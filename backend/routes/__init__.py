"""Route blueprints."""
from backend.routes.admin import bp as admin_bp
from backend.routes.auth import bp as auth_bp
from backend.routes.dashboard import bp as dashboard_bp
from backend.routes.documents import bp as documents_bp
from backend.routes.explanation import bp as explanation_bp
from backend.routes.history import bp as history_bp
from backend.routes.keywords import bp as keywords_bp
from backend.routes.language import bp as language_bp
from backend.routes.pages import bp as pages_bp
from backend.routes.reports import bp as reports_bp
from backend.routes.sentiment import bp as sentiment_bp
from backend.routes.summarization import bp as summarization_bp
from backend.routes.system import bp as system_bp
from backend.routes.translation import bp as translation_bp

ALL_BLUEPRINTS = [
    pages_bp,
    auth_bp,
    dashboard_bp,
    documents_bp,
    keywords_bp,
    summarization_bp,
    language_bp,
    sentiment_bp,
    explanation_bp,
    translation_bp,
    history_bp,
    reports_bp,
    admin_bp,
    system_bp,
]
