"""Extractive and abstractive summarisation tests."""
from __future__ import annotations

from backend.models import Analysis
from backend.services.nlp.errors import NLPUnavailableError
from tests.conftest import ACADEMIC_TEXT, GENERAL_TEXT, NEWS_TEXT


def test_extractive_summary_preserves_original_sentences(auth_client):
    response = auth_client.post(
        "/api/summarization/extractive",
        json={"text": ACADEMIC_TEXT, "length": "medium"},
    )
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["method"] == "extractive"
    assert 0 < result["summary_word_count"] < result["original_word_count"]
    assert 0 <= result["compression_percentage"] < 100
    assert result["summary"] in ACADEMIC_TEXT
    assert result["selected_sentence_indexes"] == sorted(result["selected_sentence_indexes"])
    assert result["algorithm"].startswith("TF-IDF sentence similarity")


def test_summary_length_settings_change_selection(auth_client):
    text = " ".join(GENERAL_TEXT.split(".")) + ". " + NEWS_TEXT + " " + ACADEMIC_TEXT
    short = auth_client.post("/api/summarization/extractive", json={"text": text, "length": "short"}).get_json()["data"]["result"]
    long = auth_client.post("/api/summarization/extractive", json={"text": text, "length": "long"}).get_json()["data"]["result"]
    assert short["selected_sentences"] <= long["selected_sentences"]
    assert short["summary_word_count"] <= long["summary_word_count"]


def test_extractive_single_sentence(auth_client):
    sentence = "This is a single complete sentence about natural language processing."
    response = auth_client.post("/api/summarization/extractive", json={"text": sentence, "length": "short"})
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert sentence in result["summary"]


def test_invalid_summary_length(auth_client):
    response = auth_client.post(
        "/api/summarization/extractive", json={"text": ACADEMIC_TEXT, "length": "enormous"}
    )
    assert response.status_code == 422


def test_abstractive_rejects_short_text(auth_client):
    response = auth_client.post(
        "/api/summarization/abstractive",
        json={"text": "This text is far too short for an abstractive summary.", "length": "short"},
    )
    assert response.status_code == 422
    assert "30 words" in response.get_json()["error"]["message"]


def test_abstractive_model_failure_is_reported_and_recorded(auth_client, app, monkeypatch):
    def unavailable(*args, **kwargs):
        raise NLPUnavailableError(
            "The abstractive summarisation model could not be loaded.",
            hint="Configure transformers and download the model.",
            provider="transformers",
        )

    monkeypatch.setattr("backend.routes.summarization.summarize_abstractive", unavailable)
    response = auth_client.post(
        "/api/summarization/abstractive", json={"text": ACADEMIC_TEXT, "length": "short"}
    )
    assert response.status_code == 503
    body = response.get_json()
    assert body["error"]["code"] == "service_unavailable"
    assert "could not be loaded" in body["error"]["message"]
    assert body["error"]["details"]["hint"]

    with app.app_context():
        failed = Analysis.query.filter_by(analysis_type="abstractive_summary", status="failed").first()
        assert failed is not None
        assert failed.error_message


def test_abstractive_success_is_saved(auth_client, app, monkeypatch):
    def fake_summary(text, *, length="medium", model_name=None):
        return {
            "method": "abstractive",
            "algorithm": "Hugging Face Transformers: test-model",
            "model": "test-model",
            "length_setting": length,
            "summary": "A concise generated summary of the source text.",
            "original_word_count": 100,
            "summary_word_count": 9,
            "compression_percentage": 91.0,
            "total_sentences": 8,
            "chunks_processed": 1,
            "chunk_summaries": ["A concise generated summary of the source text."],
            "note": "Generated summaries may contain inaccuracies.",
        }

    monkeypatch.setattr("backend.routes.summarization.summarize_abstractive", fake_summary)
    response = auth_client.post(
        "/api/summarization/abstractive", json={"text": ACADEMIC_TEXT, "length": "long"}
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["result"]["summary"] == "A concise generated summary of the source text."
    with app.app_context():
        analysis = Analysis.query.get(data["analysis_id"])
        assert analysis.analysis_type == "abstractive_summary"
        assert analysis.result["model"] == "test-model"
        assert analysis.status == "completed"
