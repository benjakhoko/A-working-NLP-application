"""Authentication, profile and password management."""
from __future__ import annotations

from flask import Blueprint, g, session

from backend.extensions import db, limiter
from backend.models import User, iso, utcnow
from backend.services.analysis_service import log_activity
from backend.utils.decorators import login_required
from backend.utils.responses import APIError, success
from backend.utils.validators import (
    json_body,
    validate_email,
    validate_full_name,
    validate_password,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _start_session(user: User, *, remember: bool = False) -> None:
    session.clear()
    session["user_id"] = user.id
    session.permanent = remember
    g.current_user = user


@bp.post("/register")
@limiter.limit("8 per minute")
def register():
    payload = json_body()
    full_name = validate_full_name(payload.get("full_name"))
    email = validate_email(payload.get("email"))
    password = validate_password(payload.get("password"))
    confirm = payload.get("confirm_password")
    if confirm is not None and confirm != password:
        raise APIError("Passwords do not match.", 422, "validation_error")
    if User.query.filter(db.func.lower(User.email) == email).first():
        raise APIError("An account with this email already exists.", 409, "email_taken")

    user = User(full_name=full_name, email=email, role="user")
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    log_activity(user, "account_created", "Account registered")
    db.session.commit()
    return success({"user": user.to_dict()}, "Account created successfully.", 201)


@bp.post("/login")
@limiter.limit("10 per minute")
def login():
    payload = json_body()
    email = validate_email(payload.get("email"))
    password = payload.get("password")
    if not isinstance(password, str) or not password:
        raise APIError("Password is required.", 422, "validation_error")
    remember = bool(payload.get("remember"))

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user is None or not user.check_password(password):
        # Do not reveal which credential was wrong.
        raise APIError("Incorrect email or password.", 401, "invalid_credentials")
    if not user.is_active:
        raise APIError("This account has been disabled.", 403, "account_disabled")

    user.last_login_at = utcnow()
    log_activity(user, "login", "Signed in")
    db.session.commit()
    _start_session(user, remember=remember)
    return success({"user": user.to_dict()}, "Signed in successfully.")


@bp.post("/logout")
def logout():
    user = getattr(g, "current_user", None)
    if user is not None:
        log_activity(user, "logout", "Signed out")
        db.session.commit()
    session.clear()
    return success(message="Signed out.")


@bp.get("/me")
@login_required
def me():
    user = g.current_user
    counts = {
        "documents": user.documents.count(),
        "analyses": user.analyses.count(),
    }
    data = user.to_dict()
    data["counts"] = counts
    return success({"user": data})


@bp.put("/profile")
@login_required
def update_profile():
    payload = json_body()
    user = g.current_user
    full_name = validate_full_name(payload.get("full_name", user.full_name))
    email = validate_email(payload.get("email", user.email))
    existing = User.query.filter(db.func.lower(User.email) == email, User.id != user.id).first()
    if existing:
        raise APIError("That email address is already in use.", 409, "email_taken")
    user.full_name = full_name
    user.email = email
    log_activity(user, "profile_updated", "Profile details updated")
    db.session.commit()
    return success({"user": user.to_dict()}, "Profile updated.")


@bp.post("/password")
@login_required
@limiter.limit("5 per minute")
def change_password():
    payload = json_body()
    user = g.current_user
    current = payload.get("current_password")
    new_password = validate_password(payload.get("new_password"))
    if not isinstance(current, str) or not current:
        raise APIError("Current password is required.", 422, "validation_error")
    if not user.check_password(current):
        raise APIError("Current password is incorrect.", 401, "invalid_credentials")
    if current == new_password:
        raise APIError("The new password must be different from the current password.", 422, "validation_error")
    user.set_password(new_password)
    log_activity(user, "password_changed", "Password changed")
    db.session.commit()
    # Keep the user signed in but rotate the session identifier.
    session.clear()
    session["user_id"] = user.id
    return success({"changed_at": iso(utcnow())}, "Password changed successfully.")
