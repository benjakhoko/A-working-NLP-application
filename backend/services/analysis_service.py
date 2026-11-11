"""Persistence and ownership logic for documents, analyses and activity."""
from __future__ import annotations

from sqlalchemy import func

from backend.extensions import db
from backend.models import (
    ANALYSIS_TYPES,
    ActivityLog,
    Analysis,
    AnalysisKeyword,
    Document,
    User,
    iso,
    utcnow,
)
from backend.services.nlp.preprocessing import clean_text, text_statistics, truncate
from backend.utils.responses import APIError


def get_owned_document(user: User, document_id: int, *, include_text: bool = True) -> Document:
    document = db.session.get(Document, document_id)
    if document is None:
        raise APIError("Document not found.", 404, "not_found")
    if document.user_id != user.id and not user.is_admin:
        # Deliberately return 404 to avoid confirming the existence of another user's record.
        raise APIError("Document not found.", 404, "not_found")
    return document


def get_owned_analysis(user: User, analysis_id: int) -> Analysis:
    analysis = db.session.get(Analysis, analysis_id)
    if analysis is None:
        raise APIError("Analysis not found.", 404, "not_found")
    if analysis.user_id != user.id and not user.is_admin:
        raise APIError("Analysis not found.", 404, "not_found")
    return analysis


def log_activity(user: User, action: str, description: str, *, entity_type: str | None = None, entity_id: int | None = None) -> None:
    db.session.add(
        ActivityLog(
            user_id=user.id,
            action=action,
            description=truncate(description, 250),
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def _default_title(analysis_type: str, text: str, document: Document | None) -> str:
    label = ANALYSIS_TYPES.get(analysis_type, analysis_type)
    if document is not None:
        return truncate(f"{label} — {document.filename}", 195)
    snippet = truncate(clean_text(text).split("\n")[0], 55)
    return truncate(f"{label} — {snippet}" if snippet else label, 195)


def record_analysis(
    user: User,
    *,
    analysis_type: str,
    input_text: str,
    result: dict,
    algorithm: str,
    processing_time: float,
    document: Document | None = None,
    title: str | None = None,
) -> Analysis:
    if analysis_type not in ANALYSIS_TYPES:
        raise ValueError(f"Unknown analysis type: {analysis_type}")
    analysis = Analysis(
        user_id=user.id,
        document_id=document.id if document else None,
        analysis_type=analysis_type,
        title=(title or _default_title(analysis_type, input_text, document))[:200],
        input_text=truncate(clean_text(input_text), 20_000),
        result=result,
        algorithm_used=truncate(algorithm, 80),
        processing_time=processing_time,
        status="completed",
    )
    db.session.add(analysis)
    db.session.flush()

    if analysis_type == "keywords" and isinstance(result.get("keywords"), list):
        algorithm_code = result.get("algorithm", "tfidf")
        for index, item in enumerate(result["keywords"][:50], start=1):
            db.session.add(
                AnalysisKeyword(
                    analysis_id=analysis.id,
                    keyword=str(item.get("keyword", ""))[:255],
                    relevance_score=float(item.get("relevance_score", 0.0)),
                    algorithm=str(algorithm_code)[:40],
                    rank=index,
                )
            )

    log_activity(
        user,
        "analysis_completed",
        f"{ANALYSIS_TYPES.get(analysis_type, analysis_type)} completed",
        entity_type="analysis",
        entity_id=analysis.id,
    )
    db.session.commit()
    return analysis


def record_failed_analysis(
    user: User,
    *,
    analysis_type: str,
    input_text: str,
    algorithm: str,
    error_message: str,
    processing_time: float,
    document: Document | None = None,
) -> Analysis:
    analysis = Analysis(
        user_id=user.id,
        document_id=document.id if document else None,
        analysis_type=analysis_type,
        title=_default_title(analysis_type, input_text, document),
        input_text=truncate(clean_text(input_text), 20_000),
        result=None,
        algorithm_used=truncate(algorithm, 80),
        processing_time=processing_time,
        status="failed",
        error_message=truncate(error_message, 500),
    )
    db.session.add(analysis)
    log_activity(
        user,
        "analysis_failed",
        f"{ANALYSIS_TYPES.get(analysis_type, analysis_type)} failed",
        entity_type="analysis",
        entity_id=None,
    )
    db.session.commit()
    return analysis


def dashboard_statistics(user: User, *, days: int = 14) -> dict:
    from datetime import timedelta

    documents_query = Document.query.filter_by(user_id=user.id)
    analyses_query = Analysis.query.filter_by(user_id=user.id)

    document_count = documents_query.count()
    analysis_count = analyses_query.count()
    keyword_count = (
        db.session.query(func.count(AnalysisKeyword.id))
        .join(Analysis, AnalysisKeyword.analysis_id == Analysis.id)
        .filter(Analysis.user_id == user.id)
        .scalar()
        or 0
    )
    summary_count = analyses_query.filter(
        Analysis.analysis_type.in_(["extractive_summary", "abstractive_summary"])
    ).count()
    failed_count = analyses_query.filter_by(status="failed").count()
    avg_processing = (
        db.session.query(func.avg(Analysis.processing_time))
        .filter(Analysis.user_id == user.id, Analysis.status == "completed")
        .scalar()
        or 0.0
    )

    usage_rows = (
        db.session.query(Analysis.analysis_type, func.count(Analysis.id))
        .filter(Analysis.user_id == user.id)
        .group_by(Analysis.analysis_type)
        .all()
    )
    tool_usage = [
        {
            "type": analysis_type,
            "label": ANALYSIS_TYPES.get(analysis_type, analysis_type),
            "count": count,
        }
        for analysis_type, count in sorted(usage_rows, key=lambda row: row[1], reverse=True)
    ]

    start_date = (utcnow() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    activity_rows = (
        db.session.query(Analysis.created_at)
        .filter(Analysis.user_id == user.id, Analysis.created_at >= start_date)
        .all()
    )
    counts: dict[str, int] = {}
    for (created_at,) in activity_rows:
        key = created_at.date().isoformat()
        counts[key] = counts.get(key, 0) + 1
    activity_chart = []
    for offset in range(days):
        day = (start_date + timedelta(days=offset)).date()
        activity_chart.append({"date": day.isoformat(), "count": counts.get(day.isoformat(), 0)})

    recent_analyses = (
        analyses_query.order_by(Analysis.created_at.desc()).limit(6).all()
    )
    recent_documents = documents_query.order_by(Document.created_at.desc()).limit(5).all()
    recent_activity = (
        ActivityLog.query.filter_by(user_id=user.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(8)
        .all()
    )

    return {
        "totals": {
            "documents_processed": document_count,
            "analyses_performed": analysis_count,
            "keywords_extracted": keyword_count,
            "summaries_generated": summary_count,
            "failed_analyses": failed_count,
            "average_processing_time": round(float(avg_processing), 3),
        },
        "tool_usage": tool_usage,
        "activity_chart": activity_chart,
        "recent_analyses": [analysis.to_dict() for analysis in recent_analyses],
        "recent_documents": [document.to_dict() for document in recent_documents],
        "recent_activity": [activity.to_dict() for activity in recent_activity],
        "generated_at": iso(utcnow()),
    }


def quick_text_stats(text: str) -> dict:
    return text_statistics(text)
