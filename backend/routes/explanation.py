"""Text explanation and simplification endpoint."""
from __future__ import annotations

import time

from flask import Blueprint, g

from backend.extensions import limiter
from backend.services.analysis_service import record_analysis, record_failed_analysis
from backend.services.nlp.errors import NLPUnavailableError
from backend.services.nlp.explainer import explain_text
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import choice, json_body

from backend.routes.common import optional_title, resolve_input

bp = Blueprint("explanation", __name__, url_prefix="/api/text")

MAX_EXPLANATION_CHARS = 8000


@bp.post("/explain")
@login_required
@limiter.limit("15 per minute")
def explain():
    payload = json_body()
    complexity = choice(
        payload.get("complexity"), field="Complexity", allowed={"simple", "standard", "detailed"}, default="standard"
    )
    text, document = resolve_input(payload, g.current_user)
    if len(text) > MAX_EXPLANATION_CHARS:
        raise APIError(
            f"Text explanation accepts at most {MAX_EXPLANATION_CHARS:,} characters. "
            "Shorten the passage and retry.",
            422,
            "validation_error",
        )
    started = time.perf_counter()
    try:
        result = explain_text(text, complexity=complexity)
    except NLPUnavailableError as exc:
        elapsed = time.perf_counter() - started
        record_failed_analysis(
            g.current_user,
            analysis_type="explanation",
            input_text=text,
            algorithm=complexity,
            error_message=exc.message,
            processing_time=elapsed,
            document=document,
        )
        raise APIError(
            exc.message, 503, "service_unavailable", {"hint": exc.hint, "provider": exc.provider}
        ) from exc
    except ValueError as exc:
        raise APIError(str(exc), 422, "validation_error") from exc
    elapsed = time.perf_counter() - started
    analysis = record_analysis(
        g.current_user,
        analysis_type="explanation",
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
        "Explanation generated.",
    )
