"""Keyword extraction using TF-IDF, RAKE and YAKE.

All three algorithms run on the real input text. Scores are min-max normalised
to 0-1 for display; the raw algorithm score is retained for transparency.
"""
from __future__ import annotations

import re

import numpy as np
from rake_nltk import Rake
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.preprocessing import (
    clean_text,
    sentence_tokenize,
    stopwords,
    unique_preserve_order,
)

ALGORITHMS = {
    "tfidf": {
        "label": "TF-IDF",
        "description": (
            "Term Frequency-Inverse Document Frequency computed over the document's "
            "sentences. Bigrams capture meaningful phrases."
        ),
    },
    "rake": {
        "label": "RAKE",
        "description": (
            "Rapid Automatic Keyword Extraction scores candidate phrases using word "
            "degree, word frequency and phrase length."
        ),
    },
    "yake": {
        "label": "YAKE",
        "description": (
            "Yet Another Keyword Extractor combines term frequency, position, casing "
            "and contextual co-occurrence. A lower raw score means a better keyword."
        ),
    },
}

YAKE_LANGUAGES = {
    "ar", "bg", "br", "cs", "da", "de", "el", "en", "es", "et", "fa", "fi", "fr", "ga",
    "gl", "hi", "hr", "hu", "id", "it", "ja", "ko", "lt", "lv", "nl", "no", "pl", "pt",
    "ro", "ru", "sk", "sl", "sv", "tr", "uk", "zh",
}


def _normalise(pairs: list[tuple[str, float]], *, invert: bool = False) -> list[dict]:
    if not pairs:
        return []
    values = np.array([score for _, score in pairs], dtype=float)
    if invert:  # lower is better (YAKE)
        values = -values
    low, high = float(values.min()), float(values.max())
    if high - low < 1e-12:
        normalised = np.ones_like(values)
    else:
        normalised = (values - low) / (high - low)
    return [
        {"keyword": keyword, "relevance_score": round(float(score), 4), "raw_score": round(float(raw), 6)}
        for (keyword, raw), score in zip(pairs, normalised)
    ]


def _is_meaningful(term: str) -> bool:
    words = re.findall(r"[A-Za-z\u00C0-\u024F][A-Za-z\u00C0-\u024F'\-]*", term)
    if not words:
        return False
    meaningful = [w for w in words if w.lower() not in stopwords() and len(w) > 2]
    return bool(meaningful) and len(term) >= 3


def _merge_overlaps(candidates: list[tuple[str, float]], top_n: int, *, lower_is_better: bool = False) -> list[tuple[str, float]]:
    """Collapse nested n-grams so the final list contains distinct concepts.

    A unigram such as ``artificial`` is replaced by the higher-value bigram
    ``artificial intelligence`` when both are candidates. Terms already covered
    by a selected longer phrase are dropped. This reduces the overlapping
    unigram/bigram output that raw n-gram extractors produce.
    """
    selected: list[tuple[str, float]] = []
    for term, score in candidates:
        tokens = set(term.casefold().split())
        if any(tokens <= set(existing.casefold().split()) for existing, _ in selected):
            continue
        replaced = False
        for index, (existing, _) in enumerate(selected):
            if set(existing.casefold().split()) < tokens:
                selected[index] = (term, score)
                replaced = True
                break
        if not replaced:
            selected.append((term, score))
        if len(selected) >= top_n:
            break
    selected.sort(key=lambda item: item[1], reverse=not lower_is_better)
    return selected


def extract_tfidf(text: str, top_n: int) -> list[dict]:
    sentences = [s for s in sentence_tokenize(text) if len(s.split()) >= 3]
    if len(sentences) < 2:
        sentences = [text]
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        stop_words=sorted(stopwords()),
        sublinear_tf=True,
        token_pattern=r"(?u)\b[A-Za-z][A-Za-z'\-]{1,}\b",
        lowercase=True,
        max_features=8000,
    )
    try:
        matrix = vectorizer.fit_transform(sentences)
    except ValueError as exc:  # empty vocabulary after stop-word removal
        raise NLPUnavailableError(
            "TF-IDF could not extract terms from this text (empty vocabulary).",
            hint="Provide text containing meaningful, non-stop-word terms.",
            provider="tfidf",
        ) from exc
    features = vectorizer.get_feature_names_out()
    # Mean TF-IDF across sentences rewards terms that recur in important sentences.
    scores = np.asarray(matrix.mean(axis=0)).ravel()
    candidates: list[tuple[str, float]] = []
    seen: set[str] = set()
    for term, score in sorted(zip(features, scores), key=lambda item: item[1], reverse=True):
        if score <= 0 or not _is_meaningful(term):
            continue
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        candidates.append((term, float(score)))
        if len(candidates) >= top_n * 3:
            break
    return _normalise(_merge_overlaps(candidates, top_n))


def extract_rake(text: str, top_n: int) -> list[dict]:
    try:
        rake = Rake(
            stopwords=sorted(stopwords()),
            min_length=1,
            max_length=4,
            include_repeated_phrases=False,
        )
        rake.extract_keywords_from_text(clean_text(text))
        ranked = rake.get_ranked_phrases_with_scores()
    except Exception as exc:
        raise NLPUnavailableError(
            "RAKE could not process this text.",
            hint="Check that NLTK data is installed (python scripts/setup_nlp.py).",
            provider="rake",
        ) from exc
    candidates: list[tuple[str, float]] = []
    for score, phrase in ranked:
        phrase = re.sub(r"\s+", " ", str(phrase)).strip(" .,;:!?\"'()[]")
        if not phrase or not _is_meaningful(phrase):
            continue
        candidates.append((phrase, float(score)))
        if len(candidates) >= top_n * 3:
            break
    return _normalise(_merge_overlaps(candidates, top_n))


def extract_yake(text: str, top_n: int, language: str = "en") -> list[dict]:
    import yake

    language = language if language in YAKE_LANGUAGES else "en"
    try:
        extractor = yake.KeywordExtractor(
            lan=language,
            n=3,
            dedupLim=0.9,
            dedupFunc="seqm",
            top=max(top_n * 3, 20),
            features=None,
        )
        pairs = extractor.extract_keywords(clean_text(text))
    except Exception as exc:
        raise NLPUnavailableError(
            "YAKE could not process this text.",
            hint="Try a shorter text or a language supported by YAKE.",
            provider="yake",
        ) from exc
    candidates: list[tuple[str, float]] = []
    for keyword, score in pairs:
        keyword = re.sub(r"\s+", " ", str(keyword)).strip(" .,;:!?\"'()[]")
        if not keyword or not _is_meaningful(keyword):
            continue
        candidates.append((keyword, float(score)))
        if len(candidates) >= top_n * 3:
            break
    # YAKE returns lower = more relevant, so invert during normalisation.
    return _normalise(_merge_overlaps(candidates, top_n, lower_is_better=True), invert=True)


def extract_keywords(text: str, *, algorithm: str = "tfidf", top_n: int = 12, language: str = "en") -> dict:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown keyword algorithm: {algorithm}")
    if algorithm == "tfidf":
        keywords = extract_tfidf(text, top_n)
    elif algorithm == "rake":
        keywords = extract_rake(text, top_n)
    else:
        keywords = extract_yake(text, top_n, language)

    keywords = unique_preserve_order_dicts(keywords)[:top_n]
    for rank, item in enumerate(keywords, start=1):
        item["rank"] = rank

    return {
        "algorithm": algorithm,
        "algorithm_label": ALGORITHMS[algorithm]["label"],
        "description": ALGORITHMS[algorithm]["description"],
        "language": language,
        "requested_count": top_n,
        "count": len(keywords),
        "keywords": keywords,
        "score_note": (
            "Scores are min-max normalised for comparison; 1.0 is the strongest keyword. "
            + ("YAKE raw scores are inverted because lower YAKE scores indicate better keywords."
               if algorithm == "yake" else "")
        ),
    }


def unique_preserve_order_dicts(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    output = []
    for item in items:
        key = item["keyword"].casefold()
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def compare_keywords(text: str, *, top_n: int = 10, language: str = "en") -> dict:
    results = {}
    errors = {}
    for algorithm in ALGORITHMS:
        try:
            results[algorithm] = extract_keywords(
                text, algorithm=algorithm, top_n=top_n, language=language
            )
        except NLPUnavailableError as exc:
            errors[algorithm] = exc.message
    if not results:
        raise NLPUnavailableError(
            "No keyword algorithm could process this text.", provider="keywords"
        )
    return {
        "mode": "comparison",
        "requested_count": top_n,
        "algorithms": results,
        "errors": errors,
        "note": "Algorithms use different scoring scales; compare rankings, not raw scores.",
    }
