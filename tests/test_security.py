"""Security regression tests: CSRF, headers, cookies, hashing and ownership."""
from __future__ import annotations

import re

from backend.models import Analysis, User
from tests.conftest import ACADEMIC_TEXT, upload_txt


def test_api_requires_authentication(client):
    protected = [
        ("get", "/api/dashboard/statistics"),
        ("get", "/api/documents"),
        ("post", "/api/keywords/extract"),
        ("post", "/api/summarization/extractive"),
        ("post", "/api/language/detect"),
        ("post", "/api/sentiment/analyze"),
        ("post", "/api/text/explain"),
        ("post", "/api/translation/translate"),
        ("get", "/api/history"),
        ("post", "/api/reports/generate"),
        ("get", "/api/admin/users"),
    ]
    for method, path in protected:
        response = getattr(client, method)(path, json={})
        assert response.status_code == 401, path
        assert response.get_json()["error"]["code"] == "unauthorized", path


def test_csrf_protects_state_changing_requests(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        page = client.get("/login")
        match = re.search(r'name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
        assert match, "CSRF meta token missing from page"
        token = match.group(1)

        blocked = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "Password123"},
        )
        assert blocked.status_code == 400
        assert blocked.get_json()["error"]["code"] == "csrf_error"

        allowed = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "Password123"},
            headers={"X-CSRFToken": token},
        )
        # The request passes CSRF validation and fails only on credentials.
        assert allowed.status_code == 401
        assert allowed.get_json()["error"]["code"] == "invalid_credentials"
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_csrf_does_not_block_read_requests(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    try:
        assert client.get("/login").status_code == 200
    finally:
        app.config["WTF_CSRF_ENABLED"] = False


def test_session_cookie_flags(client):
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Cookie Tester",
            "email": "cookie@example.com",
            "password": "Password123",
            "confirm_password": "Password123",
        },
    )
    assert response.status_code == 201
    cookies = response.headers.getlist("Set-Cookie")
    session_cookie = next(cookie for cookie in cookies if cookie.startswith("session="))
    assert "HttpOnly" in session_cookie
    assert "SameSite=Lax" in session_cookie


def test_password_is_stored_with_pbkdf2(app, client):
    client.post(
        "/api/auth/register",
        json={
            "full_name": "Hash Tester",
            "email": "hash@example.com",
            "password": "Password123",
            "confirm_password": "Password123",
        },
    )
    with app.app_context():
        stored = User.query.filter_by(email="hash@example.com").first()
        assert stored.password_hash.startswith("pbkdf2:sha256:600000$")
        assert "Password123" not in stored.password_hash
        assert stored.check_password("Password123")
        assert not stored.check_password("Password124")


def test_security_headers_on_api_responses(auth_client):
    response = auth_client.get("/api/auth/me")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    policy = response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy


def test_cross_user_analysis_access_is_blocked(auth_client, second_client, app):
    analysis_id = auth_client.post(
        "/api/keywords/extract", json={"text": ACADEMIC_TEXT, "top_n": 5}
    ).get_json()["data"]["analysis_id"]

    assert second_client.get(f"/api/history/{analysis_id}").status_code == 404
    assert second_client.delete(f"/api/history/{analysis_id}").status_code == 404
    assert second_client.post("/api/reports/generate", json={"analysis_id": analysis_id}).status_code == 404

    with app.app_context():
        assert Analysis.query.get(analysis_id) is not None


def test_other_users_analysis_cannot_be_used_with_document_input(auth_client, second_client):
    document_id = upload_txt(auth_client).get_json()["data"]["document"]["id"]
    response = second_client.post(
        "/api/keywords/extract", json={"document_id": document_id, "top_n": 5}
    )
    assert response.status_code == 404


def test_search_parameters_are_not_sql_injectable(auth_client):
    upload_txt(auth_client)
    payload = "' OR 1=1; DROP TABLE documents; --"
    response = auth_client.get("/api/documents", query_string={"q": payload})
    assert response.status_code == 200
    assert response.get_json()["data"]["pagination"]["total"] == 0
    # The table is still present and the original row survives.
    assert auth_client.get("/api/documents").get_json()["data"]["pagination"]["total"] == 1


def test_method_not_allowed_returns_json(auth_client):
    response = auth_client.delete("/api/auth/me")
    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "method_not_allowed"


def test_admin_endpoint_rejects_non_admin_without_leaking_data(auth_client):
    response = auth_client.get("/api/admin/users")
    assert response.status_code == 403
    assert "users" not in response.get_json()
