"""NLP service registry: capability discovery for the frontend."""
from __future__ import annotations

import importlib.util

from flask import current_app

from backend.services.nlp.keywords import ALGORITHMS
from backend.services.nlp.language_detector import SUPPORTED_CODES, language_name
from backend.services.nlp.translator import LANGUAGES, PROVIDER_LABELS, available_languages


def capabilities() -> dict:
    def installed(module: str) -> bool:
        return importlib.util.find_spec(module) is not None

    provider = current_app.config.get("TRANSLATION_PROVIDER", "mymemory")
    explanation_provider = current_app.config.get("EXPLANATION_PROVIDER", "local")
    return {
        "keyword_algorithms": [
            {"code": code, "label": meta["label"], "description": meta["description"]}
            for code, meta in ALGORITHMS.items()
        ],
        "summarization": {
            "extractive": {"available": True, "algorithm": "TF-IDF + TextRank"},
            "abstractive": {
                "available": installed("torch") and installed("transformers"),
                "model": current_app.config.get("SUMMARIZATION_MODEL"),
                "note": "Model weights download on first use.",
            },
        },
        "language_detection": {
            "available": installed("langdetect"),
            "supported_languages": [{"code": code, "name": language_name(code)} for code in SUPPORTED_CODES],
            "note": "Coverage reflects langdetect profiles, not all human languages.",
        },
        "sentiment": {
            "available": installed("nltk"),
            "method": "VADER lexicon with optional multilingual transformer",
            "multilingual_model": current_app.config.get("MULTILINGUAL_SENTIMENT_MODEL") or None,
        },
        "explanation": {
            "provider": explanation_provider,
            "model": (
                current_app.config.get("OPENAI_CHAT_MODEL")
                if explanation_provider == "openai"
                else current_app.config.get("EXPLANATION_MODEL")
            ),
            "api_configured": bool(current_app.config.get("OPENAI_API_KEY"))
            if explanation_provider == "openai"
            else True,
        },
        "translation": {
            "provider": provider,
            "provider_label": PROVIDER_LABELS.get(provider, provider),
            "languages": available_languages(),
            "language_count": len(LANGUAGES),
        },
    }
