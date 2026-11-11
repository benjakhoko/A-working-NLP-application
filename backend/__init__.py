"""Flask application factory."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from backend.extensions import csrf, db, limiter, migrate
from backend.routes import ALL_BLUEPRINTS
from backend.utils.decorators import load_current_user
from backend.utils.responses import APIError, error

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_name: str | None = None) -> Flask:
    from config import CONFIG_MAP, Config

    app = Flask(
        __name__,
        static_folder=str(BASE_DIR / "frontend" / "static"),
        template_folder=str(BASE_DIR / "frontend" / "templates"),
    )
    selected = config_name or os.getenv("FLASK_ENV", "development")
    app.config.from_object(CONFIG_MAP.get(selected, Config))
    app.config["APP_NAME"] = "Intelligent Text Analysis System"

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///") and not app.config["SQLALCHEMY_DATABASE_URI"].endswith(":memory:"):
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db.init_app(app)
    migrate.init_app(app, db, directory=str(BASE_DIR / "migrations"))
    csrf.init_app(app)
    limiter.init_app(app)
    app.json.sort_keys = False

    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)

    @app.before_request
    def _load_user():
        load_current_user()

    @app.context_processor
    def inject_globals():
        return {
            "current_user": getattr(g, "current_user", None),
            "current_year": datetime.now(timezone.utc).year,
            "app_name": app.config["APP_NAME"],
        }

    def _wants_json() -> bool:
        return request.path.startswith("/api/") or request.is_json

    @app.errorhandler(APIError)
    def handle_api_error(exc: APIError):
        if _wants_json():
            return error(exc.message, exc.status, exc.code, exc.details)
        return render_template("error.html", code=exc.status, message=exc.message), exc.status

    @app.errorhandler(CSRFError)
    def handle_csrf(exc: CSRFError):
        if _wants_json():
            return error(
                "The security token is missing or expired. Refresh the page and try again.",
                400,
                "csrf_error",
            )
        return render_template("error.html", code=400, message="Your session security token expired. Refresh and try again."), 400

    @app.errorhandler(RequestEntityTooLarge)
    def handle_413(exc):
        limit_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        message = f"The upload exceeds the {limit_mb} MB limit."
        if _wants_json():
            return error(message, 413, "file_too_large")
        return render_template("error.html", code=413, message=message), 413

    @app.errorhandler(429)
    def handle_429(exc):
        if _wants_json():
            return error("Too many requests. Please wait and try again.", 429, "rate_limited")
        return render_template("error.html", code=429, message="Too many requests. Please wait and try again."), 429

    @app.errorhandler(404)
    def handle_404(exc):
        if _wants_json():
            return error("The requested resource was not found.", 404, "not_found")
        return render_template("error.html", code=404, message="The page you requested could not be found."), 404

    @app.errorhandler(405)
    def handle_405(exc):
        if _wants_json():
            return error("This HTTP method is not allowed for the endpoint.", 405, "method_not_allowed")
        return render_template("error.html", code=405, message="Method not allowed."), 405

    @app.errorhandler(HTTPException)
    def handle_http(exc: HTTPException):
        if _wants_json():
            return error(exc.description or "Request failed.", exc.code or 400, "http_error")
        return render_template("error.html", code=exc.code or 500, message=exc.description or "Request failed."), exc.code or 500

    @app.errorhandler(Exception)
    def handle_unexpected(exc: Exception):
        app.logger.exception("Unhandled exception on %s", request.path)
        db.session.rollback()
        if _wants_json():
            return error("An unexpected server error occurred. Please try again.", 500, "internal_error")
        return render_template("error.html", code=500, message="An unexpected server error occurred."), 500

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'",
        )
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.cli.command("init-db")
    def init_db():
        """Create all tables directly (use Flask-Migrate for production)."""
        with app.app_context():
            db.create_all()
            print("Database tables created.")

    @app.cli.command("create-admin")
    def create_admin():
        """Create an administrator: flask create-admin NAME EMAIL PASSWORD."""
        import click

        from backend.models import User

        full_name = click.prompt("Full name")
        email = click.prompt("Email").lower().strip()
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        with app.app_context():
            if User.query.filter(db.func.lower(User.email) == email).first():
                raise click.ClickException("A user with that email already exists.")
            user = User(full_name=full_name, email=email, role="admin")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            print(f"Administrator {email} created.")

    @app.shell_context_processor
    def shell_context():
        from backend.models import ActivityLog, Analysis, AnalysisKeyword, Document, User

        return {
            "db": db,
            "User": User,
            "Document": Document,
            "Analysis": Analysis,
            "AnalysisKeyword": AnalysisKeyword,
            "ActivityLog": ActivityLog,
        }

    return app
