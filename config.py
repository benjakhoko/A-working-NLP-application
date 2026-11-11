"""Application configuration.

Values are read from environment variables (see .env.example). SQLite is the
zero-configuration default so the project can be demonstrated immediately;
set DATABASE_URL to a MySQL URI for the submitted / production deployment.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret")

    # MySQL is the documented production database. SQLite keeps the project
    # runnable without a database server.
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'ita_dev.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        SQLALCHEMY_ENGINE_OPTIONS = {}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_int("PERMANENT_SESSION_LIFETIME_HOURS", 8))
    MAX_CONTENT_LENGTH = _int("MAX_CONTENT_LENGTH_MB", 10) * 1024 * 1024

    # CSRF (Flask-WTF). JSON clients send the token in X-CSRFToken.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # Rate limiting (Flask-Limiter)
    RATELIMIT_ENABLED = _bool("RATELIMIT_ENABLED", True)
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "300 per hour")

    # Uploads and text limits
    MAX_TEXT_LENGTH = _int("MAX_TEXT_LENGTH", 50_000)
    MIN_TEXT_LENGTH = 3
    ALLOWED_EXTENSIONS = {"txt", "pdf", "docx"}
    ALLOWED_MIME_TYPES = {
        "txt": {"text/plain", "application/octet-stream"},
        "pdf": {"application/pdf", "application/octet-stream"},
        "docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            "application/octet-stream",
        },
    }

    # NLP model configuration
    SUMMARIZATION_MODEL = os.getenv("SUMMARIZATION_MODEL", "sshleifer/distilbart-cnn-12-6")
    EXPLANATION_MODEL = os.getenv("EXPLANATION_MODEL", "google/flan-t5-base")
    MULTILINGUAL_SENTIMENT_MODEL = os.getenv("MULTILINGUAL_SENTIMENT_MODEL", "").strip()
    EXPLANATION_PROVIDER = os.getenv("EXPLANATION_PROVIDER", "local").strip().lower()

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    TRANSLATION_PROVIDER = os.getenv("TRANSLATION_PROVIDER", "mymemory").strip().lower()
    MYMEMORY_EMAIL = os.getenv("MYMEMORY_EMAIL", "").strip()
    LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "https://libretranslate.com").rstrip("/")
    LIBRETRANSLATE_API_KEY = os.getenv("LIBRETRANSLATE_API_KEY", "").strip()
    TRANSLATION_OPENAI_MODEL = os.getenv("TRANSLATION_OPENAI_MODEL", "gpt-4o-mini")

    MODEL_TIMEOUT_SECONDS = _int("MODEL_TIMEOUT_SECONDS", 120)
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SECRET_KEY = "test-secret-key"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SERVER_NAME = "localhost"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    MAX_TEXT_LENGTH = 20_000


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
