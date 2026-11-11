"""Database models for users, documents and NLP analyses."""
from __future__ import annotations

from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import db

ANALYSIS_TYPES = {
    "keywords": "Keyword Extraction",
    "extractive_summary": "Extractive Summary",
    "abstractive_summary": "Abstractive Summary",
    "language": "Language Detection",
    "sentiment": "Sentiment Analysis",
    "explanation": "Text Explanation",
    "translation": "Translation",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    documents = db.relationship(
        "Document", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    analyses = db.relationship(
        "Analysis", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )
    activity_logs = db.relationship(
        "ActivityLog", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(
            password, method="pbkdf2:sha256:600000"
        )

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": iso(self.created_at),
            "last_login_at": iso(self.last_login_at),
        }


class Document(db.Model):
    __tablename__ = "documents"
    __table_args__ = (
        db.Index("ix_documents_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    mime_type = db.Column(db.String(120))
    extracted_text = db.Column(db.Text, nullable=False)
    word_count = db.Column(db.Integer, nullable=False)
    char_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="documents")
    analyses = db.relationship(
        "Analysis", back_populates="document", cascade="all, delete-orphan", lazy="dynamic"
    )

    def to_dict(self, *, include_text: bool = False) -> dict:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "created_at": iso(self.created_at),
        }
        if include_text:
            data["extracted_text"] = self.extracted_text
        return data


class Analysis(db.Model):
    __tablename__ = "analyses"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('completed','failed')", name="ck_analyses_status"
        ),
        db.Index("ix_analyses_type_created", "analysis_type", "created_at"),
        db.Index("ix_analyses_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id = db.Column(
        db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    analysis_type = db.Column(db.String(40), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    input_text = db.Column(db.Text)
    result = db.Column(db.JSON)
    algorithm_used = db.Column(db.String(80))
    processing_time = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(20), nullable=False, default="completed")
    error_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="analyses")
    document = db.relationship("Document", back_populates="analyses")
    keywords = db.relationship(
        "AnalysisKeyword",
        back_populates="analysis",
        cascade="all, delete-orphan",
        order_by="AnalysisKeyword.rank",
    )

    def to_dict(self, *, include_result: bool = False) -> dict:
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "document_id": self.document_id,
            "document_name": self.document.filename if self.document else None,
            "analysis_type": self.analysis_type,
            "analysis_label": ANALYSIS_TYPES.get(self.analysis_type, self.analysis_type),
            "title": self.title,
            "algorithm_used": self.algorithm_used,
            "processing_time": self.processing_time,
            "status": self.status,
            "error_message": self.error_message,
            "created_at": iso(self.created_at),
        }
        if include_result:
            data["input_text"] = self.input_text
            data["result"] = self.result
        return data


class AnalysisKeyword(db.Model):
    __tablename__ = "analysis_keywords"
    __table_args__ = (
        db.Index("ix_analysis_keywords_analysis_rank", "analysis_id", "rank"),
    )

    id = db.Column(db.Integer, primary_key=True)
    analysis_id = db.Column(
        db.Integer, db.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword = db.Column(db.String(255), nullable=False)
    relevance_score = db.Column(db.Float, nullable=False)
    algorithm = db.Column(db.String(40), nullable=False)
    rank = db.Column(db.Integer, nullable=False)

    analysis = db.relationship("Analysis", back_populates="keywords")


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"
    __table_args__ = (
        db.Index("ix_activity_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action = db.Column(db.String(60), nullable=False)
    entity_type = db.Column(db.String(40))
    entity_id = db.Column(db.Integer)
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", back_populates="activity_logs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "description": self.description,
            "created_at": iso(self.created_at),
        }
