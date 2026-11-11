"""Authentication, profile and session tests."""
from __future__ import annotations

from backend.extensions import db
from backend.models import User


def test_register_creates_user_without_signing_in(client, app):
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Nora Bennett",
            "email": "Nora@Example.com",
            "password": "StrongPass123",
            "confirm_password": "StrongPass123",
        },
    )
    assert response.status_code == 201
    body = response.get_json()
    assert body["data"]["user"]["email"] == "nora@example.com"
    assert body["data"]["user"]["role"] == "user"
    assert client.get("/api/auth/me").status_code == 401
    with app.app_context():
        user = User.query.filter_by(email="nora@example.com").first()
        assert user is not None
        assert user.password_hash != "StrongPass123"
        assert user.check_password("StrongPass123")
    login = client.post(
        "/api/auth/login",
        json={"email": "nora@example.com", "password": "StrongPass123"},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_register_rejects_duplicate_email_case_insensitively(client):
    payload = {
        "full_name": "Duplicate Person",
        "email": "duplicate@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 201
    payload["email"] = "DUPLICATE@example.com"
    payload["full_name"] = "Another Person"
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "email_taken"


def test_register_validation_errors(client):
    cases = [
        {"full_name": "A", "email": "a@b.com", "password": "StrongPass123"},
        {"full_name": "Valid Name", "email": "not-an-email", "password": "StrongPass123"},
        {"full_name": "Valid Name", "email": "x@y.com", "password": "short"},
        {"full_name": "Valid Name", "email": "x@y.com", "password": "nodigitshere"},
        {"full_name": "Valid Name", "email": "x@y.com", "password": "StrongPass123", "confirm_password": "Different123"},
    ]
    for payload in cases:
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422, payload
        assert response.get_json()["error"]["code"] == "validation_error"


def test_login_logout_and_invalid_credentials(client, user):
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    wrong = client.post("/api/auth/login", json={"email": "amina@example.com", "password": "WrongPass123"})
    assert wrong.status_code == 401
    assert "Incorrect email or password" in wrong.get_json()["error"]["message"]

    unknown = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "WrongPass123"})
    assert unknown.status_code == 401
    assert unknown.get_json()["error"]["message"] == wrong.get_json()["error"]["message"]

    success = client.post(
        "/api/auth/login",
        json={"email": "AMINA@example.com", "password": "SecurePass123", "remember": True},
    )
    assert success.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_disabled_account_cannot_login(client, app, user):
    with app.app_context():
        account = User.query.filter_by(email="amina@example.com").first()
        account.is_active = False
        db.session.commit()
    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"email": "amina@example.com", "password": "SecurePass123"})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "account_disabled"


def test_profile_update_and_email_conflict(auth_client, second_client):
    response = auth_client.put(
        "/api/auth/profile",
        json={"full_name": "Amina J. Clarke", "email": "amina.clarke@example.com"},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["full_name"] == "Amina J. Clarke"

    conflict = auth_client.put(
        "/api/auth/profile",
        json={"full_name": "Amina J. Clarke", "email": "benedict@example.com"},
    )
    assert conflict.status_code == 409


def test_password_change_flow(auth_client, user):
    wrong = auth_client.post(
        "/api/auth/password",
        json={"current_password": "NotThePassword1", "new_password": "NewSecure456"},
    )
    assert wrong.status_code == 401

    unchanged = auth_client.post(
        "/api/auth/password",
        json={"current_password": "SecurePass123", "new_password": "SecurePass123"},
    )
    assert unchanged.status_code == 422

    changed = auth_client.post(
        "/api/auth/password",
        json={"current_password": "SecurePass123", "new_password": "NewSecure456"},
    )
    assert changed.status_code == 200
    auth_client.post("/api/auth/logout")
    assert auth_client.post(
        "/api/auth/login", json={"email": "amina@example.com", "password": "SecurePass123"}
    ).status_code == 401
    assert auth_client.post(
        "/api/auth/login", json={"email": "amina@example.com", "password": "NewSecure456"}
    ).status_code == 200


def test_protected_routes_require_authentication(client):
    assert client.get("/api/dashboard/statistics").status_code == 401
    assert client.post("/api/language/detect", json={"text": "Hello world"}).status_code == 401
    page = client.get("/dashboard")
    assert page.status_code == 302
    assert "/login" in page.headers["Location"]


def test_authenticated_page_redirects_auth_pages_to_dashboard(auth_client):
    for path in ("/login", "/register"):
        response = auth_client.get(path)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/dashboard")
