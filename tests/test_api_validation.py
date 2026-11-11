"""Input validation and malformed-request tests across the API."""
from __future__ import annotations

from tests.conftest import ACADEMIC_TEXT, GENERAL_TEXT, upload_txt


def _error(response):
    return response.get_json()["error"]


def test_registration_validation(client):
    cases = [
        ({}, "required"),
        ({"full_name": "A", "email": "a@example.com", "password": "Password123"}, "Full name"),
        ({"full_name": "Valid Name", "email": "not-an-email", "password": "Password123"}, "valid email"),
        ({"full_name": "Valid Name", "email": "a@example.com", "password": "short"}, "at least 8"),
        ({"full_name": "Valid Name", "email": "a@example.com", "password": "allletters"}, "letter and one number"),
        ({"full_name": "Valid Name", "email": "a@example.com", "password": "Password123", "confirm_password": "Password124"}, "do not match"),
        ({"full_name": "Bad123", "email": "a@example.com", "password": "Password123"}, "letters"),
    ]
    for payload, fragment in cases:
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422, payload
        assert fragment.lower() in _error(response)["message"].lower(), payload


def test_duplicate_email_is_case_insensitive(client, user):
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Another Person",
            "email": "AMINA@example.com",
            "password": "Password123",
            "confirm_password": "Password123",
        },
    )
    assert response.status_code == 409
    assert _error(response)["code"] == "email_taken"


def test_non_json_body_rejected(auth_client):
    response = auth_client.post("/api/keywords/extract", data="text=hello", content_type="text/plain")
    assert response.status_code == 400
    assert _error(response)["code"] == "invalid_json"


def test_text_validation(auth_client, app):
    missing = auth_client.post("/api/keywords/extract", json={})
    assert missing.status_code == 422
    assert "Provide text" in _error(missing)["message"]

    short = auth_client.post("/api/keywords/extract", json={"text": "hi"})
    assert short.status_code == 422
    assert "at least 3" in _error(short)["message"]

    not_text = auth_client.post("/api/keywords/extract", json={"text": 42})
    assert not_text.status_code == 422
    assert "must be text" in _error(not_text)["message"]

    original_limit = app.config["MAX_TEXT_LENGTH"]
    app.config["MAX_TEXT_LENGTH"] = 20
    try:
        too_long = auth_client.post("/api/keywords/extract", json={"text": "word " * 10})
        assert too_long.status_code == 422
        assert "at most 20" in _error(too_long)["message"]
    finally:
        app.config["MAX_TEXT_LENGTH"] = original_limit


def test_document_id_validation(auth_client):
    non_numeric = auth_client.post("/api/keywords/extract", json={"document_id": "abc"})
    assert non_numeric.status_code == 422
    assert "whole number" in _error(non_numeric)["message"]

    negative = auth_client.post("/api/keywords/extract", json={"document_id": -3})
    assert negative.status_code == 422
    assert "invalid" in _error(negative)["message"]

    missing = auth_client.post("/api/keywords/extract", json={"document_id": 9999})
    assert missing.status_code == 404
    assert _error(missing)["code"] == "not_found"


def test_keyword_parameter_validation(auth_client):
    assert auth_client.post("/api/keywords/extract", json={"text": ACADEMIC_TEXT, "algorithm": "magic"}).status_code == 422
    for top_n in [2, 51, "many"]:
        response = auth_client.post("/api/keywords/extract", json={"text": ACADEMIC_TEXT, "top_n": top_n})
        assert response.status_code == 422, top_n


def test_summary_and_explanation_parameter_validation(auth_client):
    assert auth_client.post("/api/summarization/extractive", json={"text": ACADEMIC_TEXT, "length": "huge"}).status_code == 422
    assert auth_client.post("/api/text/explain", json={"text": ACADEMIC_TEXT, "complexity": "extreme"}).status_code == 422

    too_long = auth_client.post("/api/text/explain", json={"text": "word " * 1700, "complexity": "simple"})
    assert too_long.status_code == 422
    assert "8,000" in _error(too_long)["message"]


def test_translation_parameter_validation(auth_client):
    unsupported = auth_client.post(
        "/api/translation/translate",
        json={"text": ACADEMIC_TEXT, "target": "klingon", "source": "en"},
    )
    assert unsupported.status_code == 422
    assert "Unsupported target" in _error(unsupported)["message"]

    same = auth_client.post(
        "/api/translation/translate",
        json={"text": ACADEMIC_TEXT, "target": "en", "source": "en"},
    )
    assert same.status_code == 422
    assert "different" in _error(same)["message"]

    bad_provider = auth_client.post(
        "/api/translation/translate",
        json={"text": ACADEMIC_TEXT, "target": "fr", "provider": "telepathy"},
    )
    assert bad_provider.status_code == 422
    assert "provider" in _error(bad_provider)["message"].lower()


def test_document_list_filter_validation(auth_client):
    assert auth_client.get("/api/documents?file_type=exe").status_code == 422
    assert auth_client.get("/api/documents?per_page=500").status_code == 422
    assert auth_client.get("/api/documents?page=0").status_code == 422
    assert auth_client.get("/api/documents?page=abc").status_code == 422


def test_history_filter_validation(auth_client):
    assert auth_client.get("/api/history?type=unknown").status_code == 422
    assert auth_client.get("/api/history?status=pending").status_code == 422
    assert auth_client.get("/api/history?date_from=07-11-2026").status_code == 422
    assert auth_client.get("/api/history?date_from=2026-11-07&date_to=2026-11-01").status_code == 422
    assert auth_client.get("/api/history?per_page=0").status_code == 422


def test_report_parameter_validation(auth_client):
    empty = auth_client.post("/api/reports/generate", json={})
    assert empty.status_code == 422
    assert _error(empty)["code"] == "validation_error"

    too_many = auth_client.post("/api/reports/generate", json={"analysis_ids": list(range(1, 14))})
    assert too_many.status_code == 422
    assert "at most 12" in _error(too_many)["message"]

    non_numeric = auth_client.post("/api/reports/generate", json={"analysis_id": "latest"})
    assert non_numeric.status_code == 422
    assert "whole number" in _error(non_numeric)["message"]


def test_pagination_defaults_and_limits(auth_client):
    upload_txt(auth_client, GENERAL_TEXT, "one.txt")
    response = auth_client.get("/api/documents?page=1&per_page=1")
    data = response.get_json()["data"]
    assert data["pagination"] == {
        "page": 1,
        "per_page": 1,
        "total": 1,
        "pages": 1,
        "has_next": False,
        "has_prev": False,
    }
