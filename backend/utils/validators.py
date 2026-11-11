"""Input validation shared by API routes."""
from __future__ import annotations

import re
from typing import Any

from flask import current_app, request

from backend.utils.responses import APIError

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
NAME_RE = re.compile(r"^[A-Za-z\u00C0-\u024F' .\-]{2,120}$")


def json_body() -> dict:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise APIError("The request body must be a JSON object.", 400, "invalid_json")
    return payload


def clean_str(value: Any, *, field: str, min_length: int = 1, max_length: int = 255, required: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise APIError(f"{field} must be text.", 422, "validation_error")
    value = value.strip()
    if required and not value:
        raise APIError(f"{field} is required.", 422, "validation_error")
    if value and len(value) < min_length:
        raise APIError(f"{field} must contain at least {min_length} characters.", 422, "validation_error")
    if len(value) > max_length:
        raise APIError(f"{field} must be at most {max_length} characters.", 422, "validation_error")
    return value


def validate_email(value: Any) -> str:
    email = clean_str(value, field="Email", max_length=255).lower()
    if not EMAIL_RE.match(email):
        raise APIError("Enter a valid email address.", 422, "validation_error")
    return email


def validate_full_name(value: Any) -> str:
    name = clean_str(value, field="Full name", min_length=2, max_length=120)
    if not NAME_RE.match(name):
        raise APIError("Full name may only contain letters, spaces, hyphens and apostrophes.", 422, "validation_error")
    return " ".join(name.split())


def validate_password(value: Any) -> str:
    if not isinstance(value, str):
        raise APIError("Password must be text.", 422, "validation_error")
    if len(value) < 8:
        raise APIError("Password must be at least 8 characters.", 422, "validation_error")
    if len(value) > 128:
        raise APIError("Password must be at most 128 characters.", 422, "validation_error")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise APIError("Password must include at least one letter and one number.", 422, "validation_error")
    return value


def validate_text(value: Any, *, field: str = "Text", min_length: int | None = None, max_length: int | None = None) -> str:
    min_len = current_app.config["MIN_TEXT_LENGTH"] if min_length is None else min_length
    max_len = current_app.config["MAX_TEXT_LENGTH"] if max_length is None else max_length
    text = clean_str(value, field=field, min_length=min_len, max_length=max_len)
    if len(text) < min_len:
        raise APIError(f"{field} must contain at least {min_len} characters.", 422, "validation_error")
    return text


def bounded_int(value: Any, *, field: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise APIError(f"{field} must be a whole number.", 422, "validation_error")
    if not minimum <= number <= maximum:
        raise APIError(f"{field} must be between {minimum} and {maximum}.", 422, "validation_error")
    return number


def bounded_float(value: Any, *, field: str, default: float, minimum: float, maximum: float) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise APIError(f"{field} must be a number.", 422, "validation_error")
    if not minimum <= number <= maximum:
        raise APIError(f"{field} must be between {minimum} and {maximum}.", 422, "validation_error")
    return number


def choice(value: Any, *, field: str, allowed: set[str], default: str | None = None) -> str:
    selected = value if isinstance(value, str) and value.strip() else default
    if selected not in allowed:
        options = ", ".join(sorted(allowed))
        raise APIError(f"{field} must be one of: {options}.", 422, "validation_error")
    return selected


def document_id_from(payload: dict) -> int | None:
    value = payload.get("document_id")
    if value in (None, "", 0, "0"):
        return None
    try:
        document_id = int(value)
    except (TypeError, ValueError):
        raise APIError("document_id must be a whole number.", 422, "validation_error")
    if document_id < 1:
        raise APIError("document_id is invalid.", 422, "validation_error")
    return document_id
