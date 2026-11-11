"""Extractive and abstractive summarisation endpoints."""
from __future__ import annotations

import time

from flask import Blueprint, g

from backend.extensions import limiter
from backend.services.analysis_service import record_analysis, record_failed_analysis
from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.summarizer import summarize_abstractive, summarize_extractive
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import choice, json_body

from backend.routes.common import optional_title, resolve_input

bp = Blueprint("summarization", __name__, url_prefix="/api/summarization")
LENGTHS = {"short", "medium", "long"}


def _run(kind: str, payload: dict):
    length = choice(payload.get("length"), field="Summary length", allowed=LENGTHS, default="medium")
    text, document = resolve_input(payload, g.current_user)
    started = time.perf_counter()
    try:
        if kind == "extractive":
            result = summarize_extractive(text, length=length)
        else:
            result = summarize_abstractive(text, length=length)
    except ValueError as exc:
        raise APIError(str(exc), 422, "validation_error") from exc
    except NLPUnavailableError as exc:
        elapsed = time.perf_counter() - started
        record_failed_analysis(
            g.current_user,
            analysis_type=f"{kind}_summary",
            input_text=text,
            algorithm=kind,
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
        analysis_type=f"{kind}_summary",
        input_text=text,
        result=result,
        algorithm=result["algorithm"],
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
        "Summary generated successfully.",
    )


@bp.post("/extractive")
@login_required
@limiter.limit("40 per minute")
def extractive():
    return _run("extractive", json_body())


@bp.post("/abstractive")
@login_required
@limiter.limit("10 per minute")
def abstractive():
    return _run("abstractive", json_body())
