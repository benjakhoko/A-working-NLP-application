"""Extractive and abstractive summarisation.

Extractive: TF-IDF sentence similarity + PageRank (TextRank) blended with
normalised word-frequency scoring. Selected sentences keep their original
wording and document order.

Abstractive: a pretrained Hugging Face sequence-to-sequence model
(distilbart-cnn by default). Long inputs are split at sentence boundaries into
token-bounded chunks; chunk summaries are then combined.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.preprocessing import (
    clean_text,
    content_words,
    sentence_tokenize,
    text_statistics,
    truncate,
)

logger = logging.getLogger(__name__)

LENGTH_PROFILES = {
    "short": {"ratio": 0.15, "min_sentences": 1, "max_sentences": 4, "abstractive": (45, 80)},
    "medium": {"ratio": 0.25, "min_sentences": 2, "max_sentences": 8, "abstractive": (80, 140)},
    "long": {"ratio": 0.40, "min_sentences": 3, "max_sentences": 14, "abstractive": (150, 240)},
}

_model_lock = threading.Lock()
_pipelines: dict[str, Any] = {}


def _target_sentence_count(total: int, length: str) -> int:
    profile = LENGTH_PROFILES[length]
    target = round(total * profile["ratio"])
    return max(1, min(total, max(profile["min_sentences"], min(profile["max_sentences"], target))))


def _word_frequency_scores(sentences: list[str]) -> np.ndarray:
    frequencies: dict[str, int] = {}
    for sentence in sentences:
        for word in content_words(sentence):
            frequencies[word] = frequencies.get(word, 0) + 1
    if not frequencies:
        return np.ones(len(sentences), dtype=float)
    peak = max(frequencies.values())
    scores = []
    for sentence in sentences:
        words = content_words(sentence)
        scores.append(sum(frequencies.get(word, 0) / peak for word in words) / max(len(words), 1))
    return np.array(scores, dtype=float)


def _textrank_scores(sentences: list[str]) -> np.ndarray:
    if len(sentences) < 2:
        return np.ones(len(sentences), dtype=float)
    try:
        vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True)
        matrix = vectorizer.fit_transform(sentences)
        similarity = cosine_similarity(matrix)
        np.fill_diagonal(similarity, 0.0)
        # Row-normalise the sentence similarity graph.
        row_sums = similarity.sum(axis=1, keepdims=True)
        transition = np.divide(similarity, row_sums, out=np.zeros_like(similarity), where=row_sums != 0)
        scores = np.full(len(sentences), 1.0 / len(sentences))
        for _ in range(50):
            updated = 0.15 / len(sentences) + 0.85 * transition.T.dot(scores)
            if np.abs(updated - scores).sum() < 1e-8:
                scores = updated
                break
            scores = updated
        return scores
    except ValueError:
        return _word_frequency_scores(sentences)


def summarize_extractive(text: str, *, length: str = "medium") -> dict:
    text = clean_text(text)
    sentences = sentence_tokenize(text)
    if not sentences:
        raise ValueError("No sentences could be identified in the text.")

    if len(sentences) == 1:
        summary = sentences[0]
        selected = [0]
    else:
        textrank = _textrank_scores(sentences)
        frequency = _word_frequency_scores(sentences)

        def normalise(values: np.ndarray) -> np.ndarray:
            spread = values.max() - values.min()
            return (values - values.min()) / spread if spread > 1e-12 else np.ones_like(values)

        # Blend graph centrality with classical frequency scoring. A small
        # position prior favours the opening sentence, which usually carries
        # the main topic in news and academic abstracts.
        position = 1.0 + 0.08 * np.exp(-np.arange(len(sentences)) / max(len(sentences) / 3, 1))
        combined = (0.65 * normalise(textrank) + 0.35 * normalise(frequency)) * position
        target = _target_sentence_count(len(sentences), length)
        selected = sorted(np.argsort(combined)[-target:].tolist())
        summary = " ".join(sentences[index] for index in selected)

    stats = text_statistics(text)
    summary_words = len(re.findall(r"\S+", summary))
    compression = max(0.0, round((1 - summary_words / max(stats["word_count"], 1)) * 100, 1))
    return {
        "method": "extractive",
        "algorithm": "TF-IDF sentence similarity + TextRank (PageRank) with frequency blending",
        "length_setting": length,
        "summary": summary,
        "original_word_count": stats["word_count"],
        "summary_word_count": summary_words,
        "compression_percentage": compression,
        "total_sentences": len(sentences),
        "selected_sentences": len(selected),
        "selected_sentence_indexes": [index + 1 for index in selected],
        "original_statistics": stats,
        "note": "Extractive summaries reuse exact sentences from the source and may read less fluently than abstractive summaries.",
    }


def _load_summarization_pipeline(model_name: str):
    with _model_lock:
        if model_name in _pipelines:
            return _pipelines[model_name]
        try:
            import torch
            from transformers import pipeline

            logger.info("Loading summarisation model %s", model_name)
            summarizer = pipeline(
                "summarization",
                model=model_name,
                tokenizer=model_name,
                device=-1,
                torch_dtype=torch.float32,
            )
        except Exception as exc:  # network, disk or dependency failure
            logger.warning("Abstractive model unavailable: %s", exc)
            raise NLPUnavailableError(
                "The abstractive summarisation model could not be loaded.",
                hint=(
                    f"Install torch/transformers and ensure the model '{model_name}' can be downloaded. "
                    "The first run requires an internet connection."
                ),
                provider="transformers",
            ) from exc
        _pipelines[model_name] = summarizer
        return summarizer


def _chunk_sentences(sentences: list[str], tokenizer, max_tokens: int = 800) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        count = len(tokenizer.encode(sentence, add_special_tokens=False))
        if current and current_tokens + count > max_tokens:
            chunks.append(" ".join(current))
            current, current_tokens = [sentence], count
        else:
            current.append(sentence)
            current_tokens += count
    if current:
        chunks.append(" ".join(current))
    return chunks


def summarize_abstractive(text: str, *, length: str = "medium", model_name: str | None = None) -> dict:
    from flask import current_app

    model_name = model_name or current_app.config["SUMMARIZATION_MODEL"]
    text = clean_text(text)
    sentences = sentence_tokenize(text)
    if not sentences:
        raise ValueError("No sentences could be identified in the text.")

    stats = text_statistics(text)
    if stats["word_count"] < 30:
        raise ValueError("Abstractive summarisation needs at least 30 words. Use extractive mode for shorter text.")

    summarizer = _load_summarization_pipeline(model_name)
    tokenizer = summarizer.tokenizer
    chunks = _chunk_sentences(sentences, tokenizer)
    min_length, max_length = LENGTH_PROFILES[length]["abstractive"]

    chunk_summaries: list[str] = []
    try:
        for chunk in chunks:
            chunk_tokens = len(tokenizer.encode(chunk, add_special_tokens=False))
            if chunk_tokens < 20:
                chunk_summaries.append(chunk)
                continue
            # Keep generation bounds below the input length for short chunks.
            chunk_max = min(max_length, max(30, chunk_tokens // 2))
            chunk_min = min(min_length, max(12, chunk_max - 10))
            output = summarizer(
                chunk,
                max_length=chunk_max,
                min_length=chunk_min,
                do_sample=False,
                truncation=True,
                num_beams=3,
                length_penalty=1.0,
            )
            generated = output[0].get("summary_text", "").strip()
            if generated:
                chunk_summaries.append(generated)
    except Exception as exc:
        logger.exception("Abstractive summarisation failed")
        raise NLPUnavailableError(
            "The abstractive summariser failed while generating the summary.",
            hint="Try a shorter text or switch to extractive summarisation.",
            provider="transformers",
        ) from exc

    if not chunk_summaries:
        raise NLPUnavailableError(
            "The model returned an empty summary.",
            hint="Try different text or switch to extractive summarisation.",
            provider="transformers",
        )

    combined = " ".join(chunk_summaries).strip()
    # Remove duplicated sentence-like fragments produced at chunk boundaries.
    seen: set[str] = set()
    deduped: list[str] = []
    for sentence in sentence_tokenize(combined):
        key = sentence.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(sentence)
    combined = " ".join(deduped) if deduped else combined

    summary_words = len(re.findall(r"\S+", combined))
    compression = max(0.0, round((1 - summary_words / max(stats["word_count"], 1)) * 100, 1))
    return {
        "method": "abstractive",
        "algorithm": f"Hugging Face Transformers: {model_name}",
        "model": model_name,
        "length_setting": length,
        "summary": combined,
        "original_word_count": stats["word_count"],
        "summary_word_count": summary_words,
        "compression_percentage": compression,
        "total_sentences": len(sentences),
        "chunks_processed": len(chunks),
        "chunk_summaries": chunk_summaries,
        "original_statistics": stats,
        "note": "Abstractive summaries are generated text and may contain inaccuracies or omit details. Verify important facts against the source.",
    }
