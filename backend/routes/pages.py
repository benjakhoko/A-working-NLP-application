"""Server-rendered page routes (the frontend is served by Flask)."""
from __future__ import annotations

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from backend.services.analysis_service import get_owned_analysis
from backend.services.nlp.translator import available_languages
from backend.utils.decorators import admin_required, login_required
from backend.utils.responses import APIError

bp = Blueprint("pages", __name__)


@bp.get("/")
def index():
    if getattr(g, "current_user", None):
        return redirect(url_for("pages.dashboard"))
    return redirect(url_for("pages.login"))


@bp.get("/login")
def login():
    if getattr(g, "current_user", None):
        return redirect(url_for("pages.dashboard"))
    return render_template(
        "login.html",
        page_title="Sign in",
        registered=request.args.get("registered") == "1",
    )


@bp.get("/register")
def register():
    if getattr(g, "current_user", None):
        return redirect(url_for("pages.dashboard"))
    return render_template("register.html", page_title="Create account")


@bp.get("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", page_title="Dashboard", active_page="dashboard")


@bp.get("/workspace")
@login_required
def workspace():
    return render_template(
        "workspace.html",
        page_title="Text workspace",
        active_page="workspace",
        document_id=None,
        languages=available_languages(),
    )


@bp.get("/workspace/document/<int:document_id>")
@login_required
def workspace_document(document_id: int):
    return render_template(
        "workspace.html",
        page_title="Text workspace",
        active_page="workspace",
        document_id=document_id,
        languages=available_languages(),
    )


@bp.get("/documents")
@login_required
def documents():
    return render_template("documents.html", page_title="Documents", active_page="documents")


@bp.get("/history")
@login_required
def history():
    return render_template("history.html", page_title="Analysis history", active_page="history")


@bp.get("/analysis/<int:analysis_id>")
@login_required
def analysis_detail(analysis_id: int):
    try:
        get_owned_analysis(g.current_user, analysis_id)
    except APIError:
        abort(404)
    return render_template(
        "analysis.html",
        page_title="Analysis result",
        active_page="history",
        analysis_id=analysis_id,
    )


@bp.get("/profile")
@login_required
def profile():
    return render_template("profile.html", page_title="Profile & settings", active_page="profile")


@bp.get("/admin/users")
@admin_required
def admin_users():
    return render_template("admin_users.html", page_title="User administration", active_page="admin")


@bp.get("/logout")
def logout_page():
    # Logout is a state-changing POST handled by /api/auth/logout.
    return redirect(url_for("pages.dashboard"))
