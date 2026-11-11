"""Dashboard statistics and NLP capability discovery."""
from __future__ import annotations

from flask import Blueprint, g

from backend.services.analysis_service import dashboard_statistics
from backend.services.nlp import capabilities
from backend.utils.decorators import login_required
from backend.utils.responses import success

bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


@bp.get("/statistics")
@login_required
def statistics():
    return success(dashboard_statistics(g.current_user))
