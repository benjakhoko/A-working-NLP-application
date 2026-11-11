"""Shared request-to-input resolution for NLP endpoints."""
from __future__ import annotations

from backend.models import Document, User
from backend.services.analysis_service import get_owned_document
from backend.services.nlp.preprocessing import clean_text
from backend.utils.responses import APIError
from backend.utils.validators import document_id_from, validate_text


def resolve_input(payload: dict, user: User) -> tuple[str, Document | None]:
    """Return validated text and an optional owned document.

    When a document is supplied, its existence and ownership are always
    verified even if the client also sends edited text.
    """
    document_id = document_id_from(payload)
    document = get_owned_document(user, document_id) if document_id else None
    raw_text = payload.get("text")
    if raw_text is not None and not isinstance(raw_text, str):
        raise APIError("Text must be text.", 422, "validation_error")
    if isinstance(raw_text, str) and raw_text.strip():
        text = validate_text(raw_text)
    elif document is not None:
        text = validate_text(document.extracted_text)
    else:
        raise APIError("Provide text or select a document.", 422, "validation_error")
    return clean_text(text), document


def optional_title(payload: dict) -> str | None:
    value = payload.get("title")
    if isinstance(value, str) and value.strip():
        return value.strip()[:200]
    return None
