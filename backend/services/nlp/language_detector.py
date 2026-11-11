"""Language identification with langdetect.

langdetect implements a Naive Bayes classifier over character n-grams using a
profile corpus. It reports a probability per language. Very short inputs are
inherently unreliable; the service surfaces that limitation explicitly.
"""
from __future__ import annotations

import re

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0

LANGUAGE_NAMES = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali", "ca": "Catalan",
    "cs": "Czech", "cy": "Welsh", "da": "Danish", "de": "German", "el": "Greek", "en": "English",
    "es": "Spanish", "et": "Estonian", "fa": "Persian", "fi": "Finnish", "fr": "French",
    "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "kn": "Kannada", "ko": "Korean",
    "lt": "Lithuanian", "lv": "Latvian", "mk": "Macedonian", "ml": "Malayalam", "mr": "Marathi",
    "ne": "Nepali", "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak", "sl": "Slovenian",
    "so": "Somali", "sq": "Albanian", "sv": "Swedish", "sw": "Swahili", "ta": "Tamil",
    "te": "Telugu", "th": "Thai", "tl": "Tagalog", "tr": "Turkish", "uk": "Ukrainian",
    "ur": "Urdu", "vi": "Vietnamese", "zh-cn": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
    "zh": "Chinese",
}

# The set of languages with a bundled langdetect profile. This is NOT every
# human language; low-resource languages are frequently misclassified.
SUPPORTED_CODES = sorted(LANGUAGE_NAMES)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code.lower(), code.upper())


def detect_language(text: str) -> dict:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if len(cleaned) < 2:
        raise ValueError("Text is too short for reliable language detection.")
    try:
        probabilities = detect_langs(cleaned)
    except LangDetectException as exc:
        raise ValueError(
            "The language could not be identified. The text may contain only symbols, numbers, or too few words."
        ) from exc

    if not probabilities:
        raise ValueError("The language could not be identified from this text.")

    ranked = sorted(probabilities, key=lambda item: item.prob, reverse=True)
    top = ranked[0]
    alternatives = [
        {"code": item.lang, "name": language_name(item.lang), "confidence": round(item.prob, 4)}
        for item in ranked[1:4]
    ]
    letters = len(re.findall(r"[^\W\d_]", cleaned, flags=re.UNICODE))
    confidence = round(top.prob, 4)
    reliable = confidence >= 0.60 and letters >= 20
    if letters < 10:
        warning = "Very short text: language detection confidence is usually low."
    elif confidence < 0.60:
        warning = "The classifier is uncertain; the text may be too short, mixed-language, or low-resource."
    else:
        warning = None

    return {
        "code": top.lang,
        "name": language_name(top.lang),
        "confidence": confidence,
        "confidence_percentage": round(confidence * 100, 1),
        "reliable": reliable,
        "is_short_text": letters < 20,
        "alternatives": alternatives,
        "supported_language_count": len(SUPPORTED_CODES),
        "warning": warning,
        "technique": "langdetect Naive Bayes character n-gram classifier",
        "limitations": (
            "langdetect covers its bundled language profiles, not every language. "
            "Short, mixed-language or low-resource text is often misclassified."
        ),
    }
