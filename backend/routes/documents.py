"""Document upload, listing, retrieval and deletion."""
from __future__ import annotations

from flask import Blueprint, current_app, g, request

from backend.extensions import db, limiter
from backend.models import Analysis, Document
from backend.services.analysis_service import log_activity
from backend.services.document_service import extract_upload
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import bounded_int

bp = Blueprint("documents", __name__, url_prefix="/api/documents")


@bp.post("/upload")
@login_required
@limiter.limit("20 per minute")
def upload():
    file = request.files.get("file")
    if file is None:
        raise APIError("Attach a file using the 'file' form field.", 422, "validation_error")
    data = extract_upload(
        file,
        max_bytes=current_app.config["MAX_CONTENT_LENGTH"],
        max_text_length=current_app.config["MAX_TEXT_LENGTH"],
    )
    document = Document(
        user_id=g.current_user.id,
        filename=data["filename"],
        file_type=data["file_type"],
        file_size=data["file_size"],
        mime_type=data["mime_type"],
        extracted_text=data["extracted_text"],
        word_count=data["word_count"],
        char_count=data["char_count"],
    )
    db.session.add(document)
    db.session.flush()
    log_activity(
        g.current_user,
        "document_uploaded",
        f"Uploaded {document.filename}",
        entity_type="document",
        entity_id=document.id,
    )
    db.session.commit()
    payload = document.to_dict(include_text=False)
    payload["statistics"] = data["statistics"]
    return success({"document": payload}, "Document uploaded and text extracted.", 201)


@bp.get("")
@login_required
def list_documents():
    page = max(1, bounded_int(request.args.get("page"), field="Page", default=1, minimum=1, maximum=10000))
    per_page = bounded_int(request.args.get("per_page"), field="Page size", default=12, minimum=1, maximum=50)
    query = Document.query.filter_by(user_id=g.current_user.id)
    search = (request.args.get("q") or "").strip()
    if search:
        query = query.filter(Document.filename.ilike(f"%{search[:100]}%"))
    file_type = (request.args.get("file_type") or "").strip().lower()
    if file_type:
        if file_type not in current_app.config["ALLOWED_EXTENSIONS"]:
            raise APIError("Unsupported file type filter.", 422, "validation_error")
        query = query.filter(Document.file_type == file_type)
    pagination = query.order_by(Document.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return success(
        {
            "documents": [document.to_dict() for document in pagination.items],
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }
    )


@bp.get("/<int:document_id>")
@login_required
def get_document(document_id: int):
    document = Document.query.filter_by(id=document_id, user_id=g.current_user.id).first()
    if document is None:
        raise APIError("Document not found.", 404, "not_found")
    data = document.to_dict(include_text=True)
    data["analyses"] = [
        analysis.to_dict()
        for analysis in document.analyses.order_by(Analysis.created_at.desc()).limit(20)
    ]
    return success({"document": data})


@bp.delete("/<int:document_id>")
@login_required
def delete_document(document_id: int):
    document = Document.query.filter_by(id=document_id, user_id=g.current_user.id).first()
    if document is None:
        raise APIError("Document not found.", 404, "not_found")
    filename = document.filename
    db.session.delete(document)
    log_activity(g.current_user, "document_deleted", f"Deleted {filename}", entity_type="document")
    db.session.commit()
    return success(message="Document and its analyses were deleted.")
