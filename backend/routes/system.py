"""System capability metadata used by the workspace UI."""
from __future__ import annotations

from flask import Blueprint

from backend.services.nlp import capabilities
from backend.utils.decorators import login_required
from backend.utils.responses import success

bp = Blueprint("system", __name__, url_prefix="/api/system")


@bp.get("/capabilities")
@login_required
def system_capabilities():
    return success(capabilities())
