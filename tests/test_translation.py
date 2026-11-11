"""Translation provider integration tests (network calls are mocked)."""
from __future__ import annotations

from backend.models import Analysis
from backend.services.nlp.translator import translate_text
from tests.conftest import FRENCH_TEXT


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def test_translation_success_with_mymemory(auth_client, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params)
        return FakeResponse({"responseData": {"translatedText": "Hola mundo. Esta es una prueba."}, "responseStatus": 200})

    monkeypatch.setattr("backend.services.nlp.translator.requests.get", fake_get)
    response = auth_client.post(
        "/api/translation/translate",
        json={"text": "Hello world. This is a test.", "target": "es"},
    )
    assert response.status_code == 200, response.get_json()
    result = response.get_json()["data"]["result"]
    assert result["translated_text"] == "Hola mundo. Esta es una prueba."
    assert result["source_language"]["code"] == "en"
    assert result["target_language"]["code"] == "es"
    assert result["source_detected"] is True
    assert calls and calls[0]["langpair"] == "en|es"
    assert "limitations" in result


def test_translation_with_explicit_source_and_language_list(auth_client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.nlp.translator.requests.get",
        lambda *args, **kwargs: FakeResponse({"responseData": {"translatedText": "Bonjour"}}),
    )
    response = auth_client.post(
        "/api/translation/translate",
        json={"text": "Hello", "source": "en", "target": "fr"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["result"]["source_detected"] is False

    languages = auth_client.get("/api/translation/languages")
    assert languages.status_code == 200
    assert any(item["code"] == "es" for item in languages.get_json()["data"]["languages"])


def test_translation_rejects_same_language_and_unsupported_target(auth_client):
    same = auth_client.post(
        "/api/translation/translate",
        json={"text": "Hello there", "source": "en", "target": "en"},
    )
    assert same.status_code == 422
    unsupported = auth_client.post(
        "/api/translation/translate",
        json={"text": "Hello there", "source": "en", "target": "xx"},
    )
    assert unsupported.status_code == 422


def test_translation_provider_failure_is_recorded(auth_client, app, monkeypatch):
    monkeypatch.setattr(
        "backend.services.nlp.translator.requests.get",
        lambda *args, **kwargs: FakeResponse({}, status_code=500, text="quota exceeded"),
    )
    response = auth_client.post(
        "/api/translation/translate",
        json={"text": FRENCH_TEXT, "source": "fr", "target": "en"},
    )
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "service_unavailable"
    with app.app_context():
        failed = Analysis.query.filter_by(analysis_type="translation", status="failed").first()
        assert failed is not None


def test_translation_quota_message_is_surfaced(auth_client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.nlp.translator.requests.get",
        lambda *args, **kwargs: FakeResponse(
            {"responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY"}}
        ),
    )
    response = auth_client.post(
        "/api/translation/translate",
        json={"text": "Hello world", "source": "en", "target": "de"},
    )
    assert response.status_code == 503
    assert "quota" in response.get_json()["error"]["message"].lower()


def test_translation_chunks_long_text(app, monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["q"])
        return FakeResponse({"responseData": {"translatedText": params["q"]}})

    monkeypatch.setattr("backend.services.nlp.translator.requests.get", fake_get)
    with app.app_context():
        text = ("This is a sentence about natural language processing. " * 30).strip()
        result = translate_text(text, source="en", target="es")
    assert result["translated_text"]
    assert len(calls) > 1
    assert all(len(chunk.encode("utf-8")) <= 450 for chunk in calls)


def test_unknown_provider_is_rejected(auth_client):
    response = auth_client.post(
        "/api/translation/translate",
        json={"text": "Hello world", "target": "es", "provider": "invented"},
    )
    assert response.status_code == 422
