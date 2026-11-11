"""Administrator user-management tests."""
from __future__ import annotations

from backend.models import ActivityLog, User


def _second_user_id(second_client) -> int:
    return second_client.get("/api/auth/me").get_json()["data"]["user"]["id"]


def test_regular_users_cannot_use_admin_api(auth_client):
    assert auth_client.get("/api/admin/users").status_code == 403
    assert auth_client.patch("/api/admin/users/1/role", json={"role": "admin"}).status_code == 403
    assert auth_client.patch("/api/admin/users/1/status", json={"is_active": False}).status_code == 403


def test_admin_lists_and_searches_users(admin_client, second_client):
    response = admin_client.get("/api/admin/users")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["totals"]["users"] == 2
    assert data["totals"]["admins"] == 1
    assert len(data["users"]) == 2
    assert all("document_count" in item and "analysis_count" in item for item in data["users"])

    search = admin_client.get("/api/admin/users?q=benedict")
    assert search.status_code == 200
    results = search.get_json()["data"]["users"]
    assert len(results) == 1
    assert results[0]["email"] == "benedict@example.com"

    empty = admin_client.get("/api/admin/users?q=does-not-exist")
    assert empty.get_json()["data"]["users"] == []


def test_admin_can_change_another_users_role(admin_client, second_client, app):
    user_id = _second_user_id(second_client)
    response = admin_client.patch(f"/api/admin/users/{user_id}/role", json={"role": "admin"})
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["role"] == "admin"

    with app.app_context():
        assert User.query.get(user_id).role == "admin"
        assert ActivityLog.query.filter_by(action="role_changed", entity_id=user_id).count() == 1

    restored = admin_client.patch(f"/api/admin/users/{user_id}/role", json={"role": "user"})
    assert restored.status_code == 200


def test_admin_cannot_change_own_role_or_status(admin_client, user):
    own_id = user["id"]
    role = admin_client.patch(f"/api/admin/users/{own_id}/role", json={"role": "user"})
    assert role.status_code == 422
    assert "your own" in role.get_json()["error"]["message"]

    status = admin_client.patch(f"/api/admin/users/{own_id}/status", json={"is_active": False})
    assert status.status_code == 422
    assert "your own" in status.get_json()["error"]["message"]


def test_admin_role_validation(admin_client, second_client):
    user_id = _second_user_id(second_client)
    assert admin_client.patch(f"/api/admin/users/{user_id}/role", json={"role": "owner"}).status_code == 422
    assert admin_client.patch("/api/admin/users/99999/role", json={"role": "admin"}).status_code == 404


def test_deactivation_blocks_login_and_invalidates_session(admin_client, second_client, app):
    user_id = _second_user_id(second_client)
    response = admin_client.patch(f"/api/admin/users/{user_id}/status", json={"is_active": False})
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["is_active"] is False

    # An existing session is rejected on the next request.
    assert second_client.get("/api/auth/me").status_code == 401

    second_client.post("/api/auth/logout")
    login = second_client.post(
        "/api/auth/login",
        json={"email": "benedict@example.com", "password": "SecurePass456"},
    )
    assert login.status_code == 403
    assert login.get_json()["error"]["code"] == "account_disabled"

    admin_client.patch(f"/api/admin/users/{user_id}/status", json={"is_active": True})
    login = second_client.post(
        "/api/auth/login",
        json={"email": "benedict@example.com", "password": "SecurePass456"},
    )
    assert login.status_code == 200


def test_status_must_be_boolean(admin_client, second_client):
    user_id = _second_user_id(second_client)
    response = admin_client.patch(f"/api/admin/users/{user_id}/status", json={"is_active": "yes"})
    assert response.status_code == 422
    assert "true or false" in response.get_json()["error"]["message"]
