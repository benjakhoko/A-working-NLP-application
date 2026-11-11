"""Dashboard statistics and capability discovery tests."""
from __future__ import annotations

from tests.conftest import ACADEMIC_TEXT, GENERAL_TEXT, upload_txt


def test_empty_dashboard_is_scoped_to_the_user(auth_client):
    response = auth_client.get("/api/dashboard/statistics")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["totals"] == {
        "documents_processed": 0,
        "analyses_performed": 0,
        "keywords_extracted": 0,
        "summaries_generated": 0,
        "failed_analyses": 0,
        "average_processing_time": 0.0,
    }
    assert len(data["activity_chart"]) == 14
    assert all(day["count"] == 0 for day in data["activity_chart"])
    assert data["recent_analyses"] == []
    assert data["recent_documents"] == []
    assert any(item["action"] == "account_created" for item in data["recent_activity"])
    assert data["generated_at"]


def test_dashboard_reflects_real_records(auth_client):
    document_id = upload_txt(auth_client, GENERAL_TEXT).get_json()["data"]["document"]["id"]
    keyword = auth_client.post(
        "/api/keywords/extract",
        json={"document_id": document_id, "algorithm": "tfidf", "top_n": 6},
    )
    assert keyword.status_code == 200
    keyword_count = len(keyword.get_json()["data"]["result"]["keywords"])

    auth_client.post(
        "/api/summarization/extractive",
        json={"document_id": document_id, "length": "short"},
    )
    auth_client.post("/api/language/detect", json={"text": ACADEMIC_TEXT})
    auth_client.post("/api/sentiment/analyze", json={"text": "This is a wonderful result."})

    data = auth_client.get("/api/dashboard/statistics").get_json()["data"]
    assert data["totals"]["documents_processed"] == 1
    assert data["totals"]["analyses_performed"] == 4
    assert data["totals"]["keywords_extracted"] == keyword_count
    assert data["totals"]["summaries_generated"] == 1
    assert data["totals"]["failed_analyses"] == 0
    assert data["totals"]["average_processing_time"] >= 0

    usage = {item["type"]: item["count"] for item in data["tool_usage"]}
    assert usage["keywords"] == 1
    assert usage["extractive_summary"] == 1
    assert usage["language"] == 1
    assert usage["sentiment"] == 1

    assert len(data["recent_analyses"]) == 4
    assert data["recent_documents"][0]["id"] == document_id
    assert any(item["action"] == "document_uploaded" for item in data["recent_activity"])
    assert sum(day["count"] for day in data["activity_chart"]) == 4


def test_dashboard_isolated_between_users(auth_client, second_client):
    upload_txt(auth_client, GENERAL_TEXT)
    auth_client.post("/api/keywords/extract", json={"text": ACADEMIC_TEXT, "top_n": 5})
    second_data = second_client.get("/api/dashboard/statistics").get_json()["data"]
    assert second_data["totals"]["documents_processed"] == 0
    assert second_data["totals"]["analyses_performed"] == 0
    assert second_data["recent_analyses"] == []


def test_capabilities_describe_installed_nlp_stack(auth_client):
    response = auth_client.get("/api/system/capabilities")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert {item["code"] for item in data["keyword_algorithms"]} == {"tfidf", "rake", "yake"}
    assert data["summarization"]["extractive"]["available"] is True
    assert data["language_detection"]["available"] is True
    assert data["sentiment"]["available"] is True
    assert data["translation"]["language_count"] >= 20
    assert data["explanation"]["provider"] in {"local", "openai"}


def test_capabilities_require_authentication(client):
    response = client.get("/api/system/capabilities")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"
