"""Downloadable PDF analysis reports."""
from __future__ import annotations

import io
import re

from flask import Blueprint, g, send_file
from reportlab.lib.pagesizes import A4  # noqa: F401  (ensures ReportLab import early)

from backend.extensions import db, limiter
from backend.models import Analysis, Document
from backend.services.analysis_service import get_owned_analysis, get_owned_document, log_activity
from backend.services.report_service import build_report_pdf
from backend.utils.decorators import login_required
from backend.utils.responses import APIError
from backend.utils.validators import json_body

bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@bp.post("/generate")
@login_required
@limiter.limit("10 per minute")
def generate():
    payload = json_body()
    analysis_ids = payload.get("analysis_ids")
    single_id = payload.get("analysis_id")
    document_id = payload.get("document_id")

    analyses: list[Analysis] = []
    document = None
    if single_id not in (None, "", 0):
        try:
            analyses = [get_owned_analysis(g.current_user, int(single_id))]
        except (TypeError, ValueError) as exc:
            raise APIError("analysis_id must be a whole number.", 422, "validation_error") from exc
    elif isinstance(analysis_ids, list) and analysis_ids:
        if len(analysis_ids) > 12:
            raise APIError("A report may include at most 12 analyses.", 422, "validation_error")
        for value in analysis_ids:
            try:
                analyses.append(get_owned_analysis(g.current_user, int(value)))
            except (TypeError, ValueError) as exc:
                raise APIError("Every analysis id must be a whole number.", 422, "validation_error") from exc
    elif document_id not in (None, "", 0):
        try:
            document = get_owned_document(g.current_user, int(document_id))
        except (TypeError, ValueError) as exc:
            raise APIError("document_id must be a whole number.", 422, "validation_error") from exc
        analyses = (
            Analysis.query.filter_by(user_id=g.current_user.id, document_id=document.id)
            .order_by(Analysis.created_at.desc())
            .limit(12)
            .all()
        )
        if not analyses:
            raise APIError("This document has no analyses to report.", 422, "no_analyses")
    else:
        raise APIError("Provide analysis_id, analysis_ids, or document_id.", 422, "validation_error")

    if not analyses:
        raise APIError("No analyses were found for this report.", 404, "not_found")

    # Ensure consistency when a document was explicitly requested.
    if document is None and analyses[0].document_id:
        document = Document.query.get(analyses[0].document_id)
        if document and document.user_id != g.current_user.id and not g.current_user.is_admin:
            document = None

    raw_title = payload.get("title")
    title = "Intelligent Text Analysis Report"
    if isinstance(raw_title, str) and raw_title.strip():
        title = re.sub(r"[\x00-\x1f\x7f]", "", raw_title.strip())[:150]

    pdf_bytes = build_report_pdf(
        user=g.current_user,
        title=title,
        analyses=analyses,
        document=document,
    )
    log_activity(
        g.current_user,
        "report_generated",
        f"Generated PDF report with {len(analyses)} analysis record(s)",
        entity_type="analysis",
        entity_id=analyses[0].id,
    )
    db.session.commit()

    safe_title = re.sub(r"[^A-Za-z0-9_\-]+", "_", title).strip("_")[:60] or "ITA_Report"
    filename = f"{safe_title}_{analyses[0].created_at.strftime('%Y%m%d')}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )
