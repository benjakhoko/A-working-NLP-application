"""Analysis history filtering, retrieval and deletion tests."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.models import Analysis
from tests.conftest import ACADEMIC_TEXT, NEWS_TEXT, upload_txt


def _create_analyses(client):
    client.post("/api/keywords/extract", json={"text": ACADEMIC_TEXT, "algorithm": "tfidf", "top_n": 5})
    client.post("/api/summarization/extractive", json={"text": NEWS_TEXT, "length": "short"})
    client.post("/api/language/detect", json={"text": NEWS_TEXT})
    client.post("/api/sentiment/analyze", json={"text": "This is a wonderful and excellent result."})


def test_history_lists_all_analyses(auth_client):
    _create_analyses(auth_client)
    response = auth_client.get("/api/history")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["pagination"]["total"] == 4
    assert len(data["analyses"]) == 4
    assert all(item["analysis_label"] for item in data["analyses"])
    assert all("preview" in item for item in data["analyses"])


def test_history_filter_by_type_and_status(auth_client):
    _create_analyses(auth_client)
    filtered = auth_client.get("/api/history?type=keywords")
    assert filtered.status_code == 200
    data = filtered.get_json()["data"]
    assert data["pagination"]["total"] == 1
    assert data["analyses"][0]["analysis_type"] == "keywords"

    completed = auth_client.get("/api/history?status=completed")
    assert completed.get_json()["data"]["pagination"]["total"] == 4
    failed = auth_client.get("/api/history?status=failed")
    assert failed.get_json()["data"]["pagination"]["total"] == 0


def test_history_filter_by_date_and_search(auth_client):
    upload = upload_txt(auth_client)
    document = upload.get_json()["data"]["document"]
    auth_client.post(
        "/api/keywords/extract",
        json={"document_id": document["id"], "algorithm": "rake", "top_n": 5},
    )
    today = datetime.now(timezone.utc).date().isoformat()
    dated = auth_client.get(f"/api/history?date_from={today}&date_to={today}")
    assert dated.status_code == 200
    assert dated.get_json()["data"]["pagination"]["total"] == 1

    searched = auth_client.get("/api/history?q=sample")
    assert searched.get_json()["data"]["pagination"]["total"] == 1

    invalid = auth_client.get("/api/history?date_from=not-a-date")
    assert invalid.status_code == 422


def test_history_detail_and_delete(auth_client, app):
    _create_analyses(auth_client)
    listing = auth_client.get("/api/history").get_json()["data"]["analyses"]
    analysis_id = listing[0]["id"]
    detail = auth_client.get(f"/api/history/{analysis_id}")
    assert detail.status_code == 200
    item = detail.get_json()["data"]["analysis"]
    assert item["result"] is not None
    assert item["input_text"]
    assert item["status"] == "completed"

    deleted = auth_client.delete(f"/api/history/{analysis_id}")
    assert deleted.status_code == 200
    assert auth_client.get(f"/api/history/{analysis_id}").status_code == 404
    with app.app_context():
        assert Analysis.query.get(analysis_id) is None


def test_history_is_private(auth_client, second_client):
    _create_analyses(auth_client)
    analysis_id = auth_client.get("/api/history").get_json()["data"]["analyses"][0]["id"]
    assert second_client.get(f"/api/history/{analysis_id}").status_code == 404
    assert second_client.delete(f"/api/history/{analysis_id}").status_code == 404
    assert second_client.get("/api/history").get_json()["data"]["pagination"]["total"] == 0


def test_history_summary(auth_client):
    _create_analyses(auth_client)
    response = auth_client.get("/api/history/summary")
    assert response.status_code == 200
    assert response.get_json()["data"] == {"total": 4, "completed": 4, "failed": 0}


def test_history_pagination(auth_client):
    for index in range(18):
        auth_client.post("/api/language/detect", json={"text": NEWS_TEXT})
    first = auth_client.get("/api/history?page=1&per_page=5").get_json()["data"]
    second = auth_client.get("/api/history?page=2&per_page=5").get_json()["data"]
    assert first["pagination"]["pages"] == 4
    assert len(first["analyses"]) == 5
    assert first["analyses"][0]["id"] != second["analyses"][0]["id"]
