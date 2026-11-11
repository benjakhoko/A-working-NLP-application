"""Keyword extraction endpoints (TF-IDF, RAKE, YAKE, comparison)."""
from __future__ import annotations

import time

from flask import Blueprint, g

from backend.extensions import limiter
from backend.services.analysis_service import record_analysis
from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.keywords import (
    ALGORITHMS,
    YAKE_LANGUAGES,
    compare_keywords,
    extract_keywords,
)
from backend.services.nlp.language_detector import detect_language
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import bounded_int, choice, json_body

from backend.routes.common import optional_title, resolve_input

bp = Blueprint("keywords", __name__, url_prefix="/api/keywords")


@bp.post("/extract")
@login_required
@limiter.limit("40 per minute")
def extract():
    payload = json_body()
    algorithm = choice(
        payload.get("algorithm"), field="Algorithm", allowed=set(ALGORITHMS) | {"compare"}, default="tfidf"
    )
    top_n = bounded_int(payload.get("top_n"), field="Number of keywords", default=12, minimum=3, maximum=50)
    text, document = resolve_input(payload, g.current_user)

    language = payload.get("language")
    detected = None
    if not isinstance(language, str) or not language.strip():
        try:
            detected = detect_language(text)
            language = detected["code"]
        except ValueError:
            language = "en"
    else:
        language = language.strip().lower()[:10]

    started = time.perf_counter()
    try:
        if algorithm == "compare":
            result = compare_keywords(text, top_n=top_n, language=language)
        else:
            result = extract_keywords(text, algorithm=algorithm, top_n=top_n, language=language)
    except ValueError as exc:
        raise APIError(str(exc), 422, "validation_error") from exc
    except NLPUnavailableError as exc:
        raise APIError(
            exc.message, 422, "unprocessable_text", {"hint": exc.hint, "provider": exc.provider}
        ) from exc
    elapsed = time.perf_counter() - started

    warnings = []
    if algorithm in {"tfidf", "rake"} and language != "en":
        warnings.append(
            f"{ALGORITHMS[algorithm]['label']} is configured with English stop words; "
            f"results for detected language '{language}' may include language-specific stop words."
        )
    if algorithm == "yake" and language not in YAKE_LANGUAGES:
        warnings.append("YAKE does not support the detected language; English processing was used.")
    result["warnings"] = warnings
    if detected:
        result["detected_language"] = {
            "code": detected["code"],
            "name": detected["name"],
            "confidence": detected["confidence"],
        }

    algorithm_label = "Comparison (TF-IDF, RAKE, YAKE)" if algorithm == "compare" else ALGORITHMS[algorithm]["label"]
    analysis = record_analysis(
        g.current_user,
        analysis_type="keywords",
        input_text=text,
        result=result,
        algorithm=algorithm_label,
        processing_time=elapsed,
        document=document,
        title=optional_title(payload),
    )
    return success(
        {
            "analysis_id": analysis.id,
            "title": analysis.title,
            "processing_time": round(elapsed, 3),
            "input_statistics": analysis.result.get("original_statistics") if analysis.result else None,
            "result": result,
        },
        "Keywords extracted successfully.",
    )
