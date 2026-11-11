"""Analysis history with filters, detail retrieval and deletion."""
from __future__ import annotations

from datetime import datetime, time, timezone

from flask import Blueprint, g, request
from sqlalchemy import or_

from backend.extensions import db
from backend.models import ANALYSIS_TYPES, Analysis, Document
from backend.services.analysis_service import get_owned_analysis, log_activity
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import bounded_int

bp = Blueprint("history", __name__, url_prefix="/api/history")


def _parse_date(value: str, *, end_of_day: bool = False):
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise APIError("Dates must use the YYYY-MM-DD format.", 422, "validation_error") from exc
    if end_of_day:
        parsed = datetime.combine(parsed.date(), time.max)
    return parsed


def _preview(analysis: Analysis) -> str:
    result = analysis.result or {}
    kind = analysis.analysis_type
    if kind in {"extractive_summary", "abstractive_summary"}:
        return (result.get("summary") or "")[:220]
    if kind == "keywords":
        terms = [item.get("keyword", "") for item in result.get("keywords", [])[:6]]
        return ", ".join(term for term in terms if term)
    if kind == "language":
        return f"{result.get('name', 'Unknown')} ({result.get('code', '—')}), confidence {result.get('confidence_percentage', 0)}%"
    if kind == "sentiment":
        return f"{str(result.get('label', 'neutral')).capitalize()} · compound {result.get('compound_score', 0):+.3f}"
    if kind == "explanation":
        return (result.get("explanation") or "")[:220]
    if kind == "translation":
        return (result.get("translated_text") or "")[:220]
    return ""


@bp.get("")
@login_required
def list_history():
    page = max(1, bounded_int(request.args.get("page"), field="Page", default=1, minimum=1, maximum=10000))
    per_page = bounded_int(request.args.get("per_page"), field="Page size", default=15, minimum=1, maximum=50)

    query = (
        Analysis.query.outerjoin(Document, Analysis.document_id == Document.id)
        .filter(Analysis.user_id == g.current_user.id)
    )
    analysis_type = (request.args.get("type") or "").strip()
    if analysis_type:
        if analysis_type not in ANALYSIS_TYPES:
            raise APIError("Unknown analysis type filter.", 422, "validation_error")
        query = query.filter(Analysis.analysis_type == analysis_type)
    status = (request.args.get("status") or "").strip()
    if status:
        if status not in {"completed", "failed"}:
            raise APIError("Status must be 'completed' or 'failed'.", 422, "validation_error")
        query = query.filter(Analysis.status == status)
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()
    if date_from:
        query = query.filter(Analysis.created_at >= _parse_date(date_from))
    if date_to:
        query = query.filter(Analysis.created_at <= _parse_date(date_to, end_of_day=True))
    if date_from and date_to and date_from > date_to:
        raise APIError("The start date must be before the end date.", 422, "validation_error")
    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search[:100]}%"
        query = query.filter(or_(Analysis.title.ilike(like), Document.filename.ilike(like)))

    pagination = query.order_by(Analysis.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    items = []
    for analysis in pagination.items:
        item = analysis.to_dict()
        item["preview"] = _preview(analysis)
        items.append(item)

    counts = {
        analysis_type: Analysis.query.filter_by(user_id=g.current_user.id, analysis_type=analysis_type).count()
        for analysis_type in ANALYSIS_TYPES
    }
    return success(
        {
            "analyses": items,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
            "available_types": [{"code": code, "label": label} for code, label in ANALYSIS_TYPES.items()],
            "type_counts": counts,
        }
    )


@bp.get("/<int:analysis_id>")
@login_required
def get_analysis(analysis_id: int):
    analysis = get_owned_analysis(g.current_user, analysis_id)
    return success({"analysis": analysis.to_dict(include_result=True)})


@bp.delete("/<int:analysis_id>")
@login_required
def delete_analysis(analysis_id: int):
    analysis = get_owned_analysis(g.current_user, analysis_id)
    db.session.delete(analysis)
    log_activity(g.current_user, "analysis_deleted", "Analysis history entry deleted", entity_type="analysis")
    db.session.commit()
    return success(message="Analysis deleted.")


@bp.get("/summary")
@login_required
def history_summary():
    total = Analysis.query.filter_by(user_id=g.current_user.id).count()
    completed = Analysis.query.filter_by(user_id=g.current_user.id, status="completed").count()
    failed = total - completed
    return success({"total": total, "completed": completed, "failed": failed})
