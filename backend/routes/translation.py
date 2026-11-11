"""Translation endpoint and language catalogue."""
from __future__ import annotations

import time

from flask import Blueprint, g

from backend.extensions import limiter
from backend.services.analysis_service import record_analysis, record_failed_analysis
from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.translator import LANGUAGES, PROVIDER_LABELS, available_languages, translate_text
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import clean_str, json_body

from backend.routes.common import optional_title, resolve_input

bp = Blueprint("translation", __name__, url_prefix="/api/translation")


@bp.get("/languages")
@login_required
def languages():
    return success({"languages": available_languages(), "providers": PROVIDER_LABELS})


@bp.post("/translate")
@login_required
@limiter.limit("20 per minute")
def translate():
    payload = json_body()
    target = clean_str(payload.get("target"), field="Target language", max_length=10).lower()
    source = payload.get("source") or "auto"
    source = clean_str(source, field="Source language", max_length=10).lower() if source != "auto" else "auto"
    provider = payload.get("provider")
    if isinstance(provider, str) and provider.strip():
        provider = provider.strip().lower()
        if provider not in PROVIDER_LABELS:
            raise APIError("Unsupported translation provider.", 422, "validation_error")
    else:
        provider = None

    text, document = resolve_input(payload, g.current_user)
    if len(text) > 5000:
        raise APIError("Translation input must be 5,000 characters or fewer.", 422, "validation_error")

    started = time.perf_counter()
    try:
        result = translate_text(text, target=target, source=source, provider=provider)
    except ValueError as exc:
        raise APIError(str(exc), 422, "validation_error") from exc
    except NLPUnavailableError as exc:
        elapsed = time.perf_counter() - started
        record_failed_analysis(
            g.current_user,
            analysis_type="translation",
            input_text=text,
            algorithm=exc.provider or "translation",
            error_message=exc.message,
            processing_time=elapsed,
            document=document,
        )
        raise APIError(
            exc.message, 503, "service_unavailable", {"hint": exc.hint, "provider": exc.provider}
        ) from exc
    elapsed = time.perf_counter() - started

    analysis = record_analysis(
        g.current_user,
        analysis_type="translation",
        input_text=text,
        result=result,
        algorithm=result["provider_label"],
        processing_time=elapsed,
        document=document,
        title=optional_title(payload),
    )
    return success(
        {
            "analysis_id": analysis.id,
            "title": analysis.title,
            "processing_time": round(elapsed, 3),
            "result": result,
        },
        "Translation completed.",
    )
