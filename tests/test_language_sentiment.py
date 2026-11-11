"""Language identification and sentiment analysis tests."""
from __future__ import annotations

from backend.models import Analysis
from tests.conftest import ACADEMIC_TEXT, FRENCH_TEXT, NEWS_TEXT, SPANISH_TEXT


def test_english_language_detection(auth_client, app):
    response = auth_client.post("/api/language/detect", json={"text": ACADEMIC_TEXT})
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["code"] == "en"
    assert result["name"] == "English"
    assert 0 <= result["confidence"] <= 1
    assert result["reliable"] is True
    assert result["supported_language_count"] > 30
    with app.app_context():
        analysis = Analysis.query.get(response.get_json()["data"]["analysis_id"])
        assert analysis.analysis_type == "language"
        assert analysis.result["code"] == "en"


def test_spanish_and_french_detection(auth_client):
    spanish = auth_client.post("/api/language/detect", json={"text": SPANISH_TEXT})
    french = auth_client.post("/api/language/detect", json={"text": FRENCH_TEXT})
    assert spanish.status_code == 200
    assert french.status_code == 200
    assert spanish.get_json()["data"]["result"]["code"] == "es"
    assert french.get_json()["data"]["result"]["code"] == "fr"


def test_short_text_is_flagged(auth_client):
    response = auth_client.post("/api/language/detect", json={"text": "Hola"})
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["is_short_text"] is True
    assert result["warning"]
    assert result["technique"].startswith("langdetect")


def test_unidentifiable_text_returns_validation_error(auth_client):
    response = auth_client.post("/api/language/detect", json={"text": "!!! 1234 ### $$$"})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "validation_error"


def test_positive_sentiment(auth_client):
    response = auth_client.post("/api/sentiment/analyze", json={"text": "I love this wonderful, excellent product. The support team was friendly and helpful."})
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["label"] == "positive"
    assert result["compound_score"] > 0.05
    assert result["positive_score"] > result["negative_score"]
    assert result["model"].startswith("VADER")
    assert result["sentences"]
    assert "not objective" in result["disclaimer"]


def test_negative_sentiment(auth_client):
    response = auth_client.post("/api/sentiment/analyze", json={"text": "This is a terrible, frustrating and useless experience. I hate it."})
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["label"] == "negative"
    assert result["compound_score"] < -0.05
    assert result["negative_score"] > result["positive_score"]
    assert result["lexicon"]["negative_terms"]


def test_neutral_sentiment(auth_client):
    response = auth_client.post("/api/sentiment/analyze", json={"text": "The office is located on the second floor of the main building."})
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["label"] == "neutral"
    assert abs(result["compound_score"]) < 0.05


def test_non_english_text_warns_about_vader(auth_client):
    response = auth_client.post(
        "/api/sentiment/analyze",
        json={"text": "Me encanta este producto maravilloso. El servicio fue excelente y amable."},
    )
    assert response.status_code == 200
    result = response.get_json()["data"]["result"]
    assert result["language"]["code"] == "es"
    assert result["warnings"]


def test_sentiment_result_is_saved(auth_client, app):
    response = auth_client.post("/api/sentiment/analyze", json={"text": NEWS_TEXT})
    analysis_id = response.get_json()["data"]["analysis_id"]
    with app.app_context():
        analysis = Analysis.query.get(analysis_id)
        assert analysis.analysis_type == "sentiment"
        assert analysis.result["label"] in {"positive", "negative", "neutral"}
