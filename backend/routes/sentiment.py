"""Sentiment analysis endpoint."""
from __future__ import annotations

import time

from flask import Blueprint, g

from backend.extensions import limiter
from backend.services.analysis_service import record_analysis
from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.sentiment import analyze_sentiment
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import json_body

from backend.routes.common import optional_title, resolve_input

bp = Blueprint("sentiment", __name__, url_prefix="/api/sentiment")


@bp.post("/analyze")
@login_required
@limiter.limit("40 per minute")
def analyze():
    payload = json_body()
    text, document = resolve_input(payload, g.current_user)
    started = time.perf_counter()
    try:
        result = analyze_sentiment(text)
    except NLPUnavailableError as exc:
        raise APIError(
            exc.message, 503, "service_unavailable", {"hint": exc.hint, "provider": exc.provider}
        ) from exc
    except ValueError as exc:
        raise APIError(str(exc), 422, "validation_error") from exc
    elapsed = time.perf_counter() - started
    analysis = record_analysis(
        g.current_user,
        analysis_type="sentiment",
        input_text=text,
        result=result,
        algorithm=result["model"],
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
        "Sentiment analysed.",
    )
