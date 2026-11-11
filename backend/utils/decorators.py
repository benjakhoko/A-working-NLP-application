"""Session authentication and role decorators."""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for

from backend.extensions import db
from backend.models import User


def load_current_user() -> None:
    """Populate g.current_user once per request from the signed session."""
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if user is not None and not user.is_active:
        user = None
    g.current_user = user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": {"code": "unauthorized", "message": "Authentication required."}}), 401
            return redirect(url_for("pages.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not g.current_user.is_admin:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": {"code": "forbidden", "message": "Administrator access required."}}), 403
            return redirect(url_for("pages.dashboard"))
        return view(*args, **kwargs)

    return wrapped


def current_user() -> User | None:
    return getattr(g, "current_user", None)
