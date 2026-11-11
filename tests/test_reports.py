"""PDF report generation tests."""
from __future__ import annotations

import fitz

from tests.conftest import ACADEMIC_TEXT, upload_txt


def _pdf_text(payload: bytes) -> str:
    document = fitz.open(stream=payload, filetype="pdf")
    try:
        return "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()


def test_keyword_report_contains_result_content(auth_client):
    analysis = auth_client.post(
        "/api/keywords/extract", json={"text": ACADEMIC_TEXT, "algorithm": "tfidf", "top_n": 6}
    ).get_json()["data"]
    response = auth_client.post(
        "/api/reports/generate",
        json={"analysis_id": analysis["analysis_id"], "title": "Academic keyword report"},
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/pdf")
    assert response.data.startswith(b"%PDF")
    assert "attachment" in response.headers["Content-Disposition"]
    text = _pdf_text(response.data)
    assert "Academic keyword report" in text
    assert "Keyword Extraction" in text
    assert "Source text statistics" in text
    assert "Ranked keywords" in text


def test_document_report_includes_all_analyses(auth_client):
    document_id = upload_txt(auth_client).get_json()["data"]["document"]["id"]
    auth_client.post(
        "/api/summarization/extractive",
        json={"document_id": document_id, "length": "short"},
    )
    auth_client.post(
        "/api/language/detect", json={"document_id": document_id}
    )
    response = auth_client.post("/api/reports/generate", json={"document_id": document_id})
    assert response.status_code == 200
    text = _pdf_text(response.data)
    assert "Extractive Summary" in text
    assert "Language Detection" in text
    assert "sample.txt" in text


def test_report_for_multiple_analyses(auth_client):
    first = auth_client.post("/api/language/detect", json={"text": ACADEMIC_TEXT}).get_json()["data"]["analysis_id"]
    second = auth_client.post(
        "/api/sentiment/analyze", json={"text": "This is a terrible and frustrating failure."}
    ).get_json()["data"]["analysis_id"]
    response = auth_client.post("/api/reports/generate", json={"analysis_ids": [first, second]})
    assert response.status_code == 200
    text = _pdf_text(response.data)
    assert "Language Detection" in text
    assert "Sentiment Analysis" in text
    assert "Negative" in text


def test_report_requires_analyses(auth_client):
    document_id = upload_txt(auth_client).get_json()["data"]["document"]["id"]
    response = auth_client.post("/api/reports/generate", json={"document_id": document_id})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "no_analyses"


def test_report_cross_user_blocked(auth_client, second_client):
    analysis_id = auth_client.post(
        "/api/keywords/extract", json={"text": ACADEMIC_TEXT, "algorithm": "yake", "top_n": 5}
    ).get_json()["data"]["analysis_id"]
    response = second_client.post("/api/reports/generate", json={"analysis_id": analysis_id})
    assert response.status_code == 404
