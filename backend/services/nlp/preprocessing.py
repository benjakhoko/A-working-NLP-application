"""Text preprocessing and descriptive statistics.

NLTK tokenizers are used when their data packages are installed. A regex
fallback keeps the API functional (with a warning) if the corpus is missing.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Iterable

from nltk.tokenize import sent_tokenize, word_tokenize

_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F0-9][A-Za-z\u00C0-\u024F0-9'\-]*")
_SENTENCE_FALLBACK_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_SPACE_RE = re.compile(r"[ \t\u00A0]+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

FALLBACK_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", "only",
    "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should",
    "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves", "then",
    "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "will", "with", "you", "your", "yours", "yourself", "yourselves", "also", "would", "could",
    "may", "might", "must", "shall", "one", "two", "using", "used", "use", "however", "therefore",
}


def clean_text(text: str) -> str:
    """Normalise Unicode and whitespace without changing the meaning of the text."""
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    try:
        from nltk.corpus import stopwords as nltk_stopwords

        return frozenset(nltk_stopwords.words("english")) | FALLBACK_STOPWORDS
    except Exception:  # pragma: no cover - depends on local NLTK data
        return frozenset(FALLBACK_STOPWORDS)


def sentence_tokenize(text: str) -> list[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return []
    try:
        sentences = sent_tokenize(cleaned)
    except Exception:  # NLTK punkt data unavailable
        sentences = _SENTENCE_FALLBACK_RE.split(cleaned)
    if len(sentences) <= 1 and "\n" in cleaned:
        sentences = [part.strip() for part in cleaned.split("\n") if part.strip()]
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def word_tokenize_simple(text: str) -> list[str]:
    try:
        return [token for token in word_tokenize(text) if _WORD_RE.fullmatch(token)]
    except Exception:
        return _WORD_RE.findall(text)


def content_words(text: str, *, min_length: int = 3) -> list[str]:
    """Lower-cased, non-stopword, alphabetic content words."""
    return [
        token.lower()
        for token in _WORD_RE.findall(text)
        if len(token) >= min_length and token.lower() not in stopwords()
    ]


def text_statistics(text: str) -> dict:
    cleaned = clean_text(text)
    words = _WORD_RE.findall(cleaned)
    sentences = sentence_tokenize(cleaned)
    paragraphs = [block for block in re.split(r"\n\s*\n", cleaned) if block.strip()]
    if not paragraphs and cleaned:
        paragraphs = [cleaned]
    unique_words = {word.lower() for word in words}
    word_count = len(words)
    return {
        "word_count": word_count,
        "character_count": len(cleaned),
        "character_count_no_spaces": len(re.sub(r"\s", "", cleaned)),
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "unique_word_count": len(unique_words),
        "lexical_diversity": round(len(unique_words) / word_count, 3) if word_count else 0.0,
        "average_sentence_length": round(word_count / len(sentences), 1) if sentences else 0.0,
        "reading_time_minutes": max(1, round(word_count / 220)) if word_count else 0,
    }


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            output.append(value.strip())
    return output
