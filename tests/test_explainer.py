"""Explanation provider tests: success, failure and API integration."""
from __future__ import annotations

from backend.models import Analysis
from backend.services.nlp.errors import NLPUnavailableError
from tests.conftest import ACADEMIC_TEXT


def _fake_explanation(text, *, complexity="standard"):
    return {
        "explanation": "Students who sleep regularly tend to perform better in exams.",
        "complexity": complexity,
        "provider": "local",
        "provider_label": "Hugging Face Transformers (test)",
        "model": "test-model",
        "key_terms": ["sleep duration", "academic performance"],
        "disclaimer": "Generated explanations can contain errors.",
    }


def test_explanation_success_is_saved(auth_client, app, monkeypatch):
    monkeypatch.setattr("backend.routes.explanation.explain_text", _fake_explanation)
    response = auth_client.post(
        "/api/text/explain", json={"text": ACADEMIC_TEXT, "complexity": "simple"}
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["result"]["explanation"].startswith("Students")
    assert data["result"]["complexity"] == "simple"
    with app.app_context():
        analysis = Analysis.query.get(data["analysis_id"])
        assert analysis.analysis_type == "explanation"
        assert analysis.status == "completed"


def test_explanation_model_failure_returns_503(auth_client, app, monkeypatch):
    def unavailable(*args, **kwargs):
        raise NLPUnavailableError(
            "The local explanation model could not be loaded.",
            hint="Configure EXPLANATION_PROVIDER=openai or install the model.",
            provider="transformers",
        )

    monkeypatch.setattr("backend.routes.explanation.explain_text", unavailable)
    response = auth_client.post("/api/text/explain", json={"text": ACADEMIC_TEXT})
    assert response.status_code == 503
    assert response.get_json()["error"]["details"]["hint"]
    with app.app_context():
        failed = Analysis.query.filter_by(analysis_type="explanation", status="failed").first()
        assert failed is not None


def test_invalid_complexity(auth_client):
    response = auth_client.post(
        "/api/text/explain", json={"text": ACADEMIC_TEXT, "complexity": "expert"}
    )
    assert response.status_code == 422


def test_explanation_text_limit(auth_client):
    response = auth_client.post("/api/text/explain", json={"text": "word " * 2000})
    assert response.status_code == 422


def test_openai_provider_uses_configured_api(app, monkeypatch):
    from backend.services.nlp.explainer import explain_text

    app.config.update(EXPLANATION_PROVIDER="openai", OPENAI_API_KEY="test-key")

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "A clear explanation of the passage."}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"]
        return FakeResponse()

    monkeypatch.setattr("backend.services.nlp.explainer.requests.post", fake_post)
    with app.app_context():
        result = explain_text(ACADEMIC_TEXT, complexity="standard")
    assert result["provider"] == "openai"
    assert result["explanation"].startswith("A clear explanation")


def test_openai_without_key_raises(app):
    from backend.services.nlp.explainer import explain_text

    app.config.update(EXPLANATION_PROVIDER="openai", OPENAI_API_KEY="")
    with app.app_context():
        try:
            explain_text(ACADEMIC_TEXT)
        except NLPUnavailableError as exc:
            assert "credentials" in exc.message.lower()
        else:  # pragma: no cover
            raise AssertionError("Expected NLPUnavailableError")
