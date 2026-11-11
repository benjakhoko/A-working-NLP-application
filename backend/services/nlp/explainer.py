"""Text explanation and simplification.

Two providers are supported and documented:
  * local  - a pretrained Hugging Face seq2seq model (google/flan-t5-base).
  * openai - any OpenAI-compatible chat-completions API using environment keys.

If the configured provider is unavailable, the service raises an error; it never
returns a fabricated explanation.
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache

import requests

from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.keywords import extract_keywords
from backend.services.nlp.preprocessing import clean_text, truncate, unique_preserve_order

logger = logging.getLogger(__name__)

COMPLEXITY_PROMPTS = {
    "simple": (
        "Explain the passage in very simple language for a secondary-school student. "
        "Use short sentences, define required jargon, and preserve the original meaning."
    ),
    "standard": (
        "Explain the passage clearly in plain English for an informed general reader. "
        "Preserve all key facts and define important terminology."
    ),
    "detailed": (
        "Provide a detailed explanation of the passage. Clarify the main argument, "
        "supporting details, technical terminology and any assumptions. Preserve meaning."
    ),
}

_model_lock = threading.Lock()
_explanation_pipeline = None
_explanation_model_name = None


def _local_explanation(text: str, complexity: str, model_name: str) -> tuple[str, str]:
    global _explanation_pipeline, _explanation_model_name
    with _model_lock:
        if _explanation_pipeline is None or _explanation_model_name != model_name:
            try:
                import torch
                from transformers import pipeline

                logger.info("Loading explanation model %s", model_name)
                _explanation_pipeline = pipeline(
                    "text2text-generation",
                    model=model_name,
                    tokenizer=model_name,
                    device=-1,
                    torch_dtype=torch.float32,
                )
                _explanation_model_name = model_name
            except Exception as exc:
                logger.warning("Explanation model unavailable: %s", exc)
                raise NLPUnavailableError(
                    "The local explanation model could not be loaded.",
                    hint=(
                        f"Ensure transformers/torch are installed and '{model_name}' can be downloaded, "
                        "or configure EXPLANATION_PROVIDER=openai with OPENAI_API_KEY."
                    ),
                    provider="transformers",
                ) from exc

    prompt = (
        f"{COMPLEXITY_PROMPTS[complexity]}\n\nPassage:\n{truncate(text, 3500)}\n\nExplanation:"
    )
    max_new = {"simple": 180, "standard": 260, "detailed": 380}[complexity]
    try:
        output = _explanation_pipeline(
            prompt,
            max_new_tokens=max_new,
            do_sample=False,
            num_beams=2,
            truncation=True,
        )
        explanation = output[0]["generated_text"].strip()
    except Exception as exc:
        logger.exception("Local explanation generation failed")
        raise NLPUnavailableError(
            "The explanation model failed to generate a response.",
            hint="Try a shorter passage or switch the explanation provider.",
            provider="transformers",
        ) from exc
    if len(explanation.split()) < 8:
        raise NLPUnavailableError(
            "The explanation model returned an unusably short response.",
            hint="Try a longer passage or configure an API provider.",
            provider="transformers",
        )
    return explanation, model_name


def _openai_chat(system_prompt: str, user_prompt: str, *, model: str) -> str:
    from flask import current_app

    api_key = current_app.config.get("OPENAI_API_KEY", "")
    if not api_key:
        raise NLPUnavailableError(
            "The configured AI API has no credentials.",
            hint="Set OPENAI_API_KEY in .env or switch EXPLANATION_PROVIDER=local.",
            provider="openai",
        )
    url = f"{current_app.config['OPENAI_BASE_URL']}/chat/completions"
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=60,
        )
    except requests.RequestException as exc:
        raise NLPUnavailableError(
            "The explanation API could not be reached.",
            hint="Check your internet connection and OPENAI_BASE_URL.",
            provider="openai",
        ) from exc
    if response.status_code >= 400:
        raise NLPUnavailableError(
            "The explanation API rejected the request.",
            hint=f"HTTP {response.status_code}: {response.text[:200]}",
            provider="openai",
        )
    try:
        content = response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise NLPUnavailableError(
            "The explanation API returned an unexpected response.",
            provider="openai",
        ) from exc
    if not content:
        raise NLPUnavailableError("The explanation API returned an empty response.", provider="openai")
    return content


def _openai_explanation(text: str, complexity: str, model: str) -> tuple[str, str]:
    system = (
        "You are an academic writing assistant. You explain passages faithfully and "
        "never invent facts. If the passage is ambiguous, say so."
    )
    user = f"{COMPLEXITY_PROMPTS[complexity]}\n\nPassage:\n{text}\n\nReturn only the explanation."
    return _openai_chat(system, user, model=model), model


@lru_cache(maxsize=1)
def _spacy_model():
    """Load spaCy's small English model once, or return None if unavailable."""
    try:
        import spacy

        return spacy.load("en_core_web_sm")
    except Exception as exc:  # model or library missing
        logger.info("spaCy model unavailable for term highlighting: %s", exc)
        return None


def _spacy_terms(text: str, limit: int) -> list[str]:
    """Named entities, noun chunks and proper nouns identified by spaCy.

    spaCy's dependency parser provides phrase boundaries and entity labels that
    a frequency-only keyword extractor cannot see. These terms complement RAKE
    when highlighting technical terminology.
    """
    nlp = _spacy_model()
    if nlp is None:
        return []
    try:
        document = nlp(truncate(text, 5000))
    except Exception:
        return []
    candidates = [entity.text.strip() for entity in document.ents]
    candidates += [chunk.text.strip() for chunk in document.noun_chunks]
    candidates += [
        token.text.strip()
        for token in document
        if token.pos_ == "PROPN" and len(token.text) > 3
    ]
    polished = [
        term for term in unique_preserve_order(candidates)
        if 3 < len(term) <= 60 and term.lower() not in {"the", "this", "that"}
    ]
    return polished[:limit]


def key_terms_in(text: str, limit: int = 8) -> list[str]:
    try:
        result = extract_keywords(text, algorithm="rake", top_n=limit)
        terms = [item["keyword"] for item in result["keywords"]]
    except Exception:
        terms = []
    terms = _spacy_terms(text, limit) + terms
    # Prefer multi-word and longer terms for technical terminology highlighting.
    polished = [
        term for term in unique_preserve_order(terms)
        if len(term) > 3 and not term.replace(" ", "").isdigit()
    ]
    # Multi-word terms first, then longer single terms.
    polished.sort(key=lambda term: (len(term.split()) == 1, -len(term)))
    return polished[:limit]


def explain_text(text: str, *, complexity: str = "standard") -> dict:
    from flask import current_app

    if complexity not in COMPLEXITY_PROMPTS:
        raise ValueError("Unsupported complexity level.")
    text = clean_text(text)
    provider = current_app.config.get("EXPLANATION_PROVIDER", "local")
    key_terms = key_terms_in(text)

    if provider == "openai":
        model = current_app.config["OPENAI_CHAT_MODEL"]
        explanation, model_used = _openai_explanation(text, complexity, model)
        provider_label = f"OpenAI-compatible API ({model})"
    elif provider == "local":
        model = current_app.config["EXPLANATION_MODEL"]
        explanation, model_used = _local_explanation(text, complexity, model)
        provider_label = f"Hugging Face Transformers ({model})"
    else:
        raise NLPUnavailableError(
            f"Unknown explanation provider '{provider}'.",
            hint="Set EXPLANATION_PROVIDER to 'local' or 'openai'.",
            provider=provider,
        )

    return {
        "explanation": explanation,
        "complexity": complexity,
        "provider": provider,
        "provider_label": provider_label,
        "model": model_used,
        "key_terms": key_terms,
        "disclaimer": (
            "Generated explanations can contain errors or omit nuance. "
            "Always compare them with the original source."
        ),
    }
