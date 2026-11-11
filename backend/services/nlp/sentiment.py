"""Sentiment analysis with NLTK VADER (default) and optional multilingual model.

VADER is a lexicon- and rule-based analyser designed for social-media English.
Scores are model outputs, not objective measurements of a person's emotions.
"""
from __future__ import annotations

import logging
import re
import threading
from functools import lru_cache

from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.language_detector import detect_language, language_name
from backend.services.nlp.preprocessing import clean_text, sentence_tokenize, word_tokenize_simple

logger = logging.getLogger(__name__)

_transformer_lock = threading.Lock()
_transformer_pipeline = None
_transformer_model_name = None


@lru_cache(maxsize=1)
def _vader():
    try:
        from nltk.sentiment import SentimentIntensityAnalyzer

        return SentimentIntensityAnalyzer()
    except Exception as exc:
        raise NLPUnavailableError(
            "VADER sentiment lexicon is not installed.",
            hint="Run: python scripts/setup_nlp.py",
            provider="vader",
        ) from exc


def _label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def _lexicon_terms(text: str, analyzer) -> dict:
    lexical = analyzer.lexicon
    positives: dict[str, float] = {}
    negatives: dict[str, float] = {}
    for token in word_tokenize_simple(text):
        value = lexical.get(token.lower())
        if value is None:
            continue
        if value > 0:
            positives[token.lower()] = value
        elif value < 0:
            negatives[token.lower()] = value
    top_positive = sorted(positives.items(), key=lambda item: item[1], reverse=True)[:5]
    top_negative = sorted(negatives.items(), key=lambda item: item[1])[:5]
    return {
        "positive_terms": [{"term": term, "score": round(score, 3)} for term, score in top_positive],
        "negative_terms": [{"term": term, "score": round(score, 3)} for term, score in top_negative],
    }


def _transformers_sentiment(text: str, model_name: str) -> dict | None:
    global _transformer_pipeline, _transformer_model_name
    with _transformer_lock:
        if _transformer_pipeline is None or _transformer_model_name != model_name:
            try:
                import torch
                from transformers import pipeline

                logger.info("Loading multilingual sentiment model %s", model_name)
                _transformer_pipeline = pipeline(
                    "sentiment-analysis",
                    model=model_name,
                    tokenizer=model_name,
                    device=-1,
                    top_k=None,
                    truncation=True,
                    torch_dtype=torch.float32,
                )
                _transformer_model_name = model_name
            except Exception as exc:
                logger.warning("Multilingual sentiment model unavailable: %s", exc)
                return None
    try:
        raw = _transformer_pipeline(text[:2000])[0]
    except Exception as exc:
        logger.warning("Multilingual sentiment inference failed: %s", exc)
        return None
    scores = {item["label"].lower(): float(item["score"]) for item in raw}
    # cardiffnlp labels: LABEL_0 negative, LABEL_1 neutral, LABEL_2 positive
    label_map = {"label_0": "negative", "label_1": "neutral", "label_2": "positive"}
    normalised = {label_map.get(key, key): value for key, value in scores.items()}
    if not {"positive", "negative", "neutral"}.issubset(normalised):
        return None
    best = max(normalised, key=normalised.get)
    return {
        "label": best,
        "positive_score": round(normalised["positive"], 4),
        "negative_score": round(normalised["negative"], 4),
        "neutral_score": round(normalised["neutral"], 4),
        "confidence": round(normalised[best], 4),
        "model": model_name,
    }


def analyze_sentiment(text: str, *, multilingual_model: str | None = None) -> dict:
    from flask import current_app

    text = clean_text(text)
    analyzer = _vader()
    overall = analyzer.polarity_scores(text)
    sentences = []
    for sentence in sentence_tokenize(text)[:40]:
        if len(sentence.split()) < 2:
            continue
        scores = analyzer.polarity_scores(sentence)
        sentences.append(
            {
                "sentence": sentence,
                "label": _label(scores["compound"]),
                "compound": round(scores["compound"], 4),
                "positive": round(scores["pos"], 4),
                "negative": round(scores["neg"], 4),
                "neutral": round(scores["neu"], 4),
            }
        )

    try:
        detected = detect_language(text)
        language_code, language_label = detected["code"], detected["name"]
        language_confidence = detected["confidence"]
    except ValueError:
        language_code, language_label, language_confidence = None, None, None

    warnings = []
    model_used = "VADER (NLTK lexicon + rule-based)"
    source = "vader"
    transformer_result = None
    configured_model = multilingual_model if multilingual_model is not None else current_app.config.get("MULTILINGUAL_SENTIMENT_MODEL", "")
    if language_code and language_code not in {"en"} and configured_model:
        transformer_result = _transformers_sentiment(text, configured_model)
    if transformer_result:
        model_used = f"Hugging Face Transformers: {configured_model}"
        source = "transformers"
        compound = round(
            transformer_result["positive_score"] - transformer_result["negative_score"], 4
        )
        result_payload = {
            "label": transformer_result["label"],
            "positive_score": transformer_result["positive_score"],
            "negative_score": transformer_result["negative_score"],
            "neutral_score": transformer_result["neutral_score"],
            "compound_score": compound,
            "confidence": transformer_result["confidence"],
        }
    else:
        result_payload = {
            "label": _label(overall["compound"]),
            "positive_score": round(overall["pos"], 4),
            "negative_score": round(overall["neg"], 4),
            "neutral_score": round(overall["neu"], 4),
            "compound_score": round(overall["compound"], 4),
            "confidence": round(abs(overall["compound"]), 4),
        }
        if language_code and language_code != "en":
            warnings.append(
                "VADER is tuned for English. Treat this result as indicative only for "
                f"{language_label or language_code} text."
            )

    return {
        "method": source,
        "model": model_used,
        "label": result_payload["label"],
        "positive_score": result_payload["positive_score"],
        "negative_score": result_payload["negative_score"],
        "neutral_score": result_payload["neutral_score"],
        "compound_score": result_payload["compound_score"],
        "confidence": result_payload["confidence"],
        "intensity": round(abs(result_payload["compound_score"]), 4),
        "language": {"code": language_code, "name": language_label, "confidence": language_confidence},
        "sentences": sentences,
        "lexicon": _lexicon_terms(text, analyzer),
        "warnings": warnings,
        "disclaimer": (
            "Sentiment scores are statistical model outputs about the language used, "
            "not objective measurements of a person's emotions or intent."
        ),
    }
