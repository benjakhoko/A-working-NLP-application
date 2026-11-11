"""Translation through a configurable provider.

Supported providers:
  * mymemory       - free public MyMemory API (no key, daily quota, best for demos)
  * libretranslate - self-hosted or hosted LibreTranslate instance
  * openai         - OpenAI-compatible chat model
  * local          - Helsinki-NLP MarianMT model downloaded on demand

No provider returns invented translations: failures surface as HTTP 503 errors.
"""
from __future__ import annotations

import html
import logging
import re
import threading

import requests

from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.language_detector import detect_language
from backend.services.nlp.preprocessing import clean_text, sentence_tokenize, truncate

logger = logging.getLogger(__name__)

LANGUAGES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "it": "Italian", "nl": "Dutch", "ru": "Russian", "ar": "Arabic", "zh": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)", "ja": "Japanese", "ko": "Korean", "hi": "Hindi",
    "tr": "Turkish", "pl": "Polish", "sv": "Swedish", "id": "Indonesian", "vi": "Vietnamese",
    "th": "Thai", "uk": "Ukrainian", "ro": "Romanian", "el": "Greek", "he": "Hebrew",
    "fa": "Persian", "bn": "Bengali", "ur": "Urdu", "sw": "Swahili", "cs": "Czech",
    "da": "Danish", "fi": "Finnish", "no": "Norwegian", "hu": "Hungarian", "bg": "Bulgarian",
    "sk": "Slovak", "ms": "Malay", "tl": "Filipino", "ta": "Tamil", "te": "Telugu",
    "ml": "Malayalam", "gu": "Gujarati", "mr": "Marathi", "pa": "Punjabi", "ne": "Nepali",
    "ka": "Georgian", "az": "Azerbaijani", "kk": "Kazakh", "uz": "Uzbek", "sr": "Serbian",
    "hr": "Croatian", "sl": "Slovenian", "lt": "Lithuanian", "lv": "Latvian", "et": "Estonian",
    "ca": "Catalan", "gl": "Galician", "af": "Afrikaans", "sq": "Albanian", "mk": "Macedonian",
    "is": "Icelandic", "ga": "Irish", "mt": "Maltese", "cy": "Welsh", "be": "Belarusian",
    "hy": "Armenian", "mn": "Mongolian", "km": "Khmer", "lo": "Lao", "my": "Burmese",
}

PROVIDER_LABELS = {
    "mymemory": "MyMemory translation API",
    "libretranslate": "LibreTranslate API",
    "openai": "OpenAI-compatible API",
    "local": "Helsinki-NLP MarianMT (local)",
}

REVERSE_NAMES = {name.lower(): code for code, name in LANGUAGES.items()}

_local_lock = threading.Lock()
_local_models: dict[str, object] = {}


def available_languages() -> list[dict]:
    return [{"code": code, "name": name} for code, name in sorted(LANGUAGES.items(), key=lambda item: item[1])]


def _normalise_code(code: str | None) -> str | None:
    if not code:
        return None
    code = code.lower()
    if code.startswith("zh"):
        return "zh" if code in {"zh", "zh-cn"} else "zh-tw"
    return code.split("-")[0]


def _chunk_text(text: str, max_bytes: int = 450) -> list[str]:
    """Split text into API-friendly chunks at sentence boundaries."""
    sentences = sentence_tokenize(text) or [text]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate.encode("utf-8")) > max_bytes:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    # Extremely long single sentences are split by words.
    final: list[str] = []
    for chunk in chunks:
        if len(chunk.encode("utf-8")) <= max_bytes:
            final.append(chunk)
            continue
        words = chunk.split()
        buffer: list[str] = []
        for word in words:
            candidate = " ".join(buffer + [word])
            if buffer and len(candidate.encode("utf-8")) > max_bytes:
                final.append(" ".join(buffer))
                buffer = [word]
            else:
                buffer.append(word)
        if buffer:
            final.append(" ".join(buffer))
    return final


def _translate_mymemory(text: str, source: str, target: str) -> str:
    from flask import current_app

    source_pair = "zh-CN" if source == "zh" else source
    target_pair = "zh-CN" if target == "zh" else target
    outputs = []
    for chunk in _chunk_text(text):
        params = {"q": chunk, "langpair": f"{source_pair}|{target_pair}"}
        email = current_app.config.get("MYMEMORY_EMAIL")
        if email:
            params["de"] = email
        try:
            response = requests.get(
                "https://api.mymemory.translated.net/get", params=params, timeout=30
            )
        except requests.RequestException as exc:
            raise NLPUnavailableError(
                "The MyMemory translation API could not be reached.",
                hint="Check your internet connection or configure a different TRANSLATION_PROVIDER.",
                provider="mymemory",
            ) from exc
        if response.status_code >= 400:
            raise NLPUnavailableError(
                "The MyMemory translation API rejected the request.",
                hint=f"HTTP {response.status_code}. The free API has daily quotas.",
                provider="mymemory",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise NLPUnavailableError(
                "The MyMemory translation API returned an unreadable response.",
                provider="mymemory",
            ) from exc
        translated = (payload.get("responseData") or {}).get("translatedText", "")
        if not translated:
            details = payload.get("responseDetails") or "No translation returned."
            raise NLPUnavailableError(
                "The MyMemory translation API returned no translation.",
                hint=str(details)[:250],
                provider="mymemory",
            )
        if re.search(r"MYMEMORY WARNING|QUERY LENGTH LIMIT|INVALID LANGUAGE PAIR", translated, re.I):
            raise NLPUnavailableError(
                "The MyMemory free quota or request limit was reached.",
                hint=translated[:250],
                provider="mymemory",
            )
        outputs.append(html.unescape(translated))
    return " ".join(outputs).strip()


def _translate_libretranslate(text: str, source: str, target: str) -> str:
    from flask import current_app

    url = current_app.config["LIBRETRANSLATE_URL"].rstrip("/") + "/translate"
    payload = {
        "q": text,
        "source": source,
        "target": target,
        "format": "text",
    }
    api_key = current_app.config.get("LIBRETRANSLATE_API_KEY")
    if api_key:
        payload["api_key"] = api_key
    try:
        response = requests.post(url, json=payload, timeout=45)
    except requests.RequestException as exc:
        raise NLPUnavailableError(
            "The LibreTranslate service could not be reached.",
            hint="Check LIBRETRANSLATE_URL and your connection.",
            provider="libretranslate",
        ) from exc
    if response.status_code >= 400:
        raise NLPUnavailableError(
            "LibreTranslate rejected the translation request.",
            hint=f"HTTP {response.status_code}: {response.text[:200]}",
            provider="libretranslate",
        )
    try:
        translated = response.json().get("translatedText", "")
    except (ValueError, AttributeError) as exc:
        raise NLPUnavailableError(
            "LibreTranslate returned an unexpected response.", provider="libretranslate"
        ) from exc
    if not translated:
        raise NLPUnavailableError("LibreTranslate returned an empty translation.", provider="libretranslate")
    return translated


def _translate_openai(text: str, source_name: str, target_name: str) -> str:
    from flask import current_app

    api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not api_key:
        raise NLPUnavailableError(
            "The translation API has no credentials.",
            hint="Set OPENAI_API_KEY or configure a different TRANSLATION_PROVIDER.",
            provider="openai",
        )
    url = f"{current_app.config['OPENAI_BASE_URL']}/chat/completions"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": current_app.config["TRANSLATION_OPENAI_MODEL"],
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a professional translator. Translate faithfully, preserve "
                            "paragraph breaks, and return only the translation."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Translate from {source_name} to {target_name}:\n\n{text}",
                    },
                ],
                "temperature": 0,
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        raise NLPUnavailableError(
            "The translation API could not be reached.", provider="openai"
        ) from exc
    if response.status_code >= 400:
        raise NLPUnavailableError(
            "The translation API rejected the request.",
            hint=f"HTTP {response.status_code}: {response.text[:200]}",
            provider="openai",
        )
    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise NLPUnavailableError(
            "The translation API returned an unexpected response.", provider="openai"
        ) from exc
    if not content:
        raise NLPUnavailableError("The translation API returned an empty translation.", provider="openai")
    return content


def _translate_local(text: str, source: str, target: str) -> str:
    model_name = f"Helsinki-NLP/opus-mt-{source}-{target}"
    with _local_lock:
        model = _local_models.get(model_name)
        if model is None:
            try:
                import torch
                from transformers import pipeline

                logger.info("Loading translation model %s", model_name)
                model = pipeline(
                    "translation",
                    model=model_name,
                    tokenizer=model_name,
                    device=-1,
                    torch_dtype=torch.float32,
                )
            except Exception as exc:
                raise NLPUnavailableError(
                    f"No local translation model is available for {source} -> {target}.",
                    hint=(
                        "MarianMT models exist for specific language pairs only. "
                        "Configure a translation API for broader coverage."
                    ),
                    provider="local",
                ) from exc
            _local_models[model_name] = model
    try:
        outputs = []
        for chunk in _chunk_text(text, max_bytes=1800):
            outputs.append(model(chunk, max_length=512)[0]["translation_text"])
        return " ".join(outputs)
    except Exception as exc:
        raise NLPUnavailableError(
            "The local translation model failed to generate a translation.",
            provider="local",
        ) from exc


def translate_text(
    text: str,
    *,
    target: str,
    source: str = "auto",
    provider: str | None = None,
) -> dict:
    from flask import current_app

    text = clean_text(text)
    if len(text) > 5000:
        raise ValueError("Translation input must be 5,000 characters or fewer.")
    provider = (provider or current_app.config.get("TRANSLATION_PROVIDER", "mymemory")).lower()
    if provider not in PROVIDER_LABELS:
        raise NLPUnavailableError(
            f"Unknown translation provider '{provider}'.",
            hint="Set TRANSLATION_PROVIDER to mymemory, libretranslate, openai or local.",
            provider=provider,
        )

    target = _normalise_code(target)
    if target not in LANGUAGES:
        raise ValueError("Unsupported target language. Choose a language from the supported list.")

    detected = None
    if not source or source == "auto":
        detected = detect_language(text)
        source = _normalise_code(detected["code"])
        source_was_detected = True
    else:
        source = _normalise_code(source)
        source_was_detected = False
    if source not in LANGUAGES:
        raise ValueError("Unsupported source language.")
    if source == target:
        raise ValueError("Source and target languages must be different.")

    source_name, target_name = LANGUAGES[source], LANGUAGES[target]
    if provider == "mymemory":
        translated = _translate_mymemory(text, source, target)
    elif provider == "libretranslate":
        translated = _translate_libretranslate(text, source, target)
    elif provider == "openai":
        translated = _translate_openai(text, source_name, target_name)
    else:
        translated = _translate_local(text, source, target)

    translated = truncate(translated.strip(), 20_000)
    return {
        "translated_text": translated,
        "source_language": {"code": source, "name": source_name},
        "target_language": {"code": target, "name": target_name},
        "source_detected": source_was_detected,
        "detection_confidence": detected["confidence"] if detected else None,
        "provider": provider,
        "provider_label": PROVIDER_LABELS[provider],
        "character_count": len(translated),
        "limitations": (
            "Machine translation can mistranslate idioms, named entities, and technical terms. "
            "Low-resource languages and specialised domains are less reliable. "
            + ("The free MyMemory API has daily quotas." if provider == "mymemory" else "")
        ),
    }
