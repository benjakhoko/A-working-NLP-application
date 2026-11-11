"""Keyword extraction API and algorithm tests."""
from __future__ import annotations

import pytest

from backend.models import Analysis, AnalysisKeyword
from tests.conftest import ACADEMIC_TEXT, NEWS_TEXT, upload_txt


@pytest.mark.parametrize("algorithm", ["tfidf", "rake", "yake"])
def test_keyword_algorithms_return_ranked_results(auth_client, app, algorithm):
    response = auth_client.post(
        "/api/keywords/extract",
        json={"text": ACADEMIC_TEXT, "algorithm": algorithm, "top_n": 8},
    )
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    result = data["result"]
    assert result["algorithm"] == algorithm
    assert 0 < result["count"] <= 8
    assert [item["rank"] for item in result["keywords"]] == list(range(1, result["count"] + 1))
    scores = [item["relevance_score"] for item in result["keywords"]]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= score <= 1.0 for score in scores)
    assert all(item["keyword"].strip() for item in result["keywords"])

    with app.app_context():
        analysis = Analysis.query.get(data["analysis_id"])
        assert analysis is not None
        assert analysis.analysis_type == "keywords"
        assert analysis.status == "completed"
        saved = AnalysisKeyword.query.filter_by(analysis_id=analysis.id).all()
        assert len(saved) == result["count"]


def test_keyword_comparison_contains_all_algorithms(auth_client):
    response = auth_client.post(
        "/api/keywords/extract",
        json={"text": NEWS_TEXT, "algorithm": "compare", "top_n": 6},
    )
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["mode"] == "comparison"
    assert set(result["algorithms"]) == {"tfidf", "rake", "yake"}
    for data in result["algorithms"].values():
        assert data["count"] <= 6


def test_keywords_are_associated_with_owned_document(auth_client, app):
    upload = upload_txt(auth_client)
    document_id = upload.get_json()["data"]["document"]["id"]
    response = auth_client.post(
        "/api/keywords/extract",
        json={"document_id": document_id, "algorithm": "tfidf", "top_n": 5},
    )
    assert response.status_code == 200
    analysis_id = response.get_json()["data"]["analysis_id"]
    with app.app_context():
        analysis = Analysis.query.get(analysis_id)
        assert analysis.document_id == document_id


def test_keywords_cannot_use_another_users_document(auth_client, second_client):
    upload = upload_txt(auth_client)
    document_id = upload.get_json()["data"]["document"]["id"]
    response = second_client.post(
        "/api/keywords/extract",
        json={"document_id": document_id, "algorithm": "tfidf", "top_n": 5},
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ACADEMIC_TEXT, "algorithm": "unknown"},
        {"text": ACADEMIC_TEXT, "algorithm": "tfidf", "top_n": 2},
        {"text": ACADEMIC_TEXT, "algorithm": "tfidf", "top_n": 100},
        {"text": "ab", "algorithm": "tfidf"},
    ],
)
def test_keyword_validation(auth_client, payload):
    response = auth_client.post("/api/keywords/extract", json=payload)
    assert response.status_code in {400, 422}
    assert response.get_json()["success"] is False


def test_stopword_only_text_returns_clear_error(auth_client):
    response = auth_client.post(
        "/api/keywords/extract",
        json={"text": "the and of to in is are was were for with", "algorithm": "tfidf"},
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "unprocessable_text"


def test_non_english_keyword_warning(auth_client):
    response = auth_client.post(
        "/api/keywords/extract",
        json={
            "text": "La investigación científica avanza gracias a la cooperación internacional entre universidades.",
            "algorithm": "tfidf",
            "top_n": 5,
        },
    )
    assert response.status_code == 200
    warnings = response.get_json()["data"]["result"]["warnings"]
    assert any("English stop words" in warning for warning in warnings)
