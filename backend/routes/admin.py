"""Administrator-only user management."""
from __future__ import annotations

from flask import Blueprint, g, request

from backend.extensions import db, limiter
from backend.models import Analysis, Document, User
from backend.services.analysis_service import log_activity
from backend.utils.decorators import admin_required
from backend.utils.responses import APIError, success
from backend.utils.validators import bounded_int, choice, json_body

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/users")
@admin_required
def list_users():
    page = max(1, bounded_int(request.args.get("page"), field="Page", default=1, minimum=1, maximum=10000))
    per_page = bounded_int(request.args.get("per_page"), field="Page size", default=20, minimum=1, maximum=100)
    query = User.query
    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search[:100]}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.email.ilike(like)))
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    users = []
    for user in pagination.items:
        item = user.to_dict()
        item["document_count"] = Document.query.filter_by(user_id=user.id).count()
        item["analysis_count"] = Analysis.query.filter_by(user_id=user.id).count()
        item["is_active"] = user.is_active
        users.append(item)
    return success(
        {
            "users": users,
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "total": pagination.total,
                "pages": pagination.pages,
            },
            "totals": {
                "users": User.query.count(),
                "admins": User.query.filter_by(role="admin").count(),
                "analyses": Analysis.query.count(),
            },
        }
    )


@bp.patch("/users/<int:user_id>/role")
@admin_required
@limiter.limit("20 per minute")
def update_role(user_id: int):
    payload = json_body()
    role = choice(payload.get("role"), field="Role", allowed={"user", "admin"}, default="user")
    user = db.session.get(User, user_id)
    if user is None:
        raise APIError("User not found.", 404, "not_found")
    if user.id == g.current_user.id:
        raise APIError("You cannot change your own administrator role.", 422, "validation_error")
    user.role = role
    log_activity(
        g.current_user,
        "role_changed",
        f"Changed role for {user.email} to {role}",
        entity_type="user",
        entity_id=user.id,
    )
    db.session.commit()
    return success({"user": user.to_dict()}, "Role updated.")


@bp.patch("/users/<int:user_id>/status")
@admin_required
@limiter.limit("20 per minute")
def update_status(user_id: int):
    payload = json_body()
    active = payload.get("is_active")
    if not isinstance(active, bool):
        raise APIError("is_active must be true or false.", 422, "validation_error")
    user = db.session.get(User, user_id)
    if user is None:
        raise APIError("User not found.", 404, "not_found")
    if user.id == g.current_user.id:
        raise APIError("You cannot deactivate your own account.", 422, "validation_error")
    user.is_active = active
    log_activity(
        g.current_user,
        "status_changed",
        f"{'Activated' if active else 'Deactivated'} {user.email}",
        entity_type="user",
        entity_id=user.id,
    )
    db.session.commit()
    return success({"user": user.to_dict()}, "Account status updated.")
