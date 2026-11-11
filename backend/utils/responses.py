"""Consistent JSON response helpers and typed API errors."""
from __future__ import annotations

from typing import Any

from flask import jsonify


class APIError(Exception):
    """Raised inside routes/services for a controlled JSON error response."""

    def __init__(self, message: str, status: int = 400, code: str = "bad_request", details: Any = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.details = details


def success(data: Any = None, message: str | None = None, status: int = 200, **extra):
    payload: dict[str, Any] = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload), status


def error(message: str, status: int = 400, code: str = "bad_request", details: Any = None, **extra):
    payload: dict[str, Any] = {"success": False, "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    payload.update(extra)
    return jsonify(payload), status
