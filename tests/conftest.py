"""Shared pytest fixtures and NLP test corpora."""
from __future__ import annotations

import io

import pytest

from backend import create_app
from backend.extensions import db
from backend.models import User


NEWS_TEXT = (
    "The city council approved a new public transport plan on Tuesday. "
    "The plan will add twelve electric buses and extend two tram lines by 2027. "
    "Officials said the changes are expected to reduce congestion and lower emissions. "
    "Local businesses welcomed the investment but asked for clearer construction timelines. "
    "The transport minister praised the project as a model for other mid-sized cities."
)

ACADEMIC_TEXT = (
    "This study examines the relationship between sleep duration and academic performance "
    "among undergraduate students. A sample of 420 participants completed weekly sleep diaries "
    "and standardised assessments over one semester. The results indicate a positive association "
    "between consistent sleep schedules and higher examination scores. However, the cross-sectional "
    "design limits causal inference. Future research should employ randomised controlled trials "
    "to evaluate targeted sleep interventions in educational settings."
)

GENERAL_TEXT = (
    "Baking bread at home is simpler than many people expect. You need flour, water, yeast and salt. "
    "Mix the ingredients, knead the dough for ten minutes, and let it rise until it doubles in size. "
    "Shape the loaf, score the top, and bake it in a hot oven. The result is a crusty bread that "
    "tastes far better than most supermarket alternatives."
)

SPANISH_TEXT = (
    "El gobierno anunció nuevas medidas para mejorar la educación pública en las zonas rurales. "
    "Las escuelas recibirán materiales, formación docente y acceso a internet de alta velocidad. "
    "Los expertos consideran que la inversión es necesaria para reducir las desigualdades regionales."
)

FRENCH_TEXT = (
    "La recherche scientifique progresse grâce à la coopération internationale. "
    "Les universités partagent des données et des ressources pour accélérer les découvertes. "
    "Cette collaboration est essentielle pour répondre aux défis climatiques mondiaux."
)

SENTIMENT_POSITIVE = (
    "I absolutely loved this product. It works beautifully, feels premium, and exceeded my expectations. "
    "The support team was helpful and friendly throughout the entire process."
)

SENTIMENT_NEGATIVE = (
    "This was a terrible experience. The device broke within a week, the support team ignored my emails, "
    "and the refund process was frustrating and slow."
)

SENTIMENT_NEUTRAL = "The office is located on the second floor of the main building."


@pytest.fixture()
def app():
    application = create_app("testing")
    application.config.update(
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
        TESTING=True,
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(client):
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Amina Clarke",
            "email": "amina@example.com",
            "password": "SecurePass123",
            "confirm_password": "SecurePass123",
        },
    )
    assert response.status_code == 201, response.get_json()
    login_response = client.post(
        "/api/auth/login",
        json={"email": "amina@example.com", "password": "SecurePass123"},
    )
    assert login_response.status_code == 200, login_response.get_json()
    return response.get_json()["data"]["user"]


@pytest.fixture()
def auth_client(client, user):
    """A logged-in client whose session belongs to the `user` fixture."""
    return client


@pytest.fixture()
def second_client(app):
    other = app.test_client()
    response = other.post(
        "/api/auth/register",
        json={
            "full_name": "Benedict Osei",
            "email": "benedict@example.com",
            "password": "SecurePass456",
            "confirm_password": "SecurePass456",
        },
    )
    assert response.status_code == 201, response.get_json()
    login_response = other.post(
        "/api/auth/login",
        json={"email": "benedict@example.com", "password": "SecurePass456"},
    )
    assert login_response.status_code == 200, login_response.get_json()
    return other


@pytest.fixture()
def admin_client(app, client, user):
    # The `app` fixture keeps one application context (and therefore one
    # SQLAlchemy session) alive for the whole test. Promoting the account in a
    # nested context would leave the outer session with a stale identity map.
    account = User.query.filter_by(email="amina@example.com").first()
    account.role = "admin"
    db.session.commit()
    return client


def upload_txt(client, text: str = GENERAL_TEXT, filename: str = "sample.txt"):
    return client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(text.encode("utf-8")), filename, "text/plain")},
        content_type="multipart/form-data",
    )


def make_pdf_bytes(text: str = NEWS_TEXT) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Helvetica", 10)
    y = 800
    for line in text.split(". "):
        pdf.drawString(50, y, line[:100])
        y -= 18
    pdf.save()
    return buffer.getvalue()


def make_docx_bytes(text: str = GENERAL_TEXT) -> bytes:
    from docx import Document

    document = Document()
    for paragraph in text.split("\n"):
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
