"""Server-rendered page routing and access-control tests."""
from __future__ import annotations

from tests.conftest import ACADEMIC_TEXT, upload_txt


def test_anonymous_visitors_are_redirected_to_login(client):
    for path in ["/", "/dashboard", "/workspace", "/documents", "/history", "/profile", "/admin/users"]:
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"], path


def test_login_and_register_pages_render_with_csrf_token(client):
    for path, marker in [("/login", "Sign in to your workspace"), ("/register", "Create your account")]:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert marker in html
        assert 'name="csrf-token"' in html
        assert 'meta name="viewport"' in html


def test_login_page_shows_account_created_notice(client):
    response = client.get("/login?registered=1")
    assert response.status_code == 200
    assert "Your account was created. Sign in to continue." in response.get_data(as_text=True)


def test_authenticated_pages_render(auth_client):
    document_id = upload_txt(auth_client).get_json()["data"]["document"]["id"]
    analysis_id = auth_client.post(
        "/api/keywords/extract", json={"text": ACADEMIC_TEXT, "top_n": 5}
    ).get_json()["data"]["analysis_id"]

    expectations = {
        "/dashboard": "Dashboard",
        "/workspace": "Text workspace",
        f"/workspace/document/{document_id}": "Text workspace",
        "/documents": "Documents",
        "/history": "Analysis history",
        f"/analysis/{analysis_id}": "Analysis result",
        "/profile": "Profile",
    }
    for path, marker in expectations.items():
        response = auth_client.get(path)
        assert response.status_code == 200, path
        assert marker in response.get_data(as_text=True), path
        assert "Verba" in response.get_data(as_text=True)


def test_analysis_page_hides_other_users_records(auth_client, second_client):
    analysis_id = auth_client.post(
        "/api/keywords/extract", json={"text": ACADEMIC_TEXT, "top_n": 5}
    ).get_json()["data"]["analysis_id"]
    assert second_client.get(f"/analysis/{analysis_id}").status_code == 404


def test_admin_page_requires_administrator(app, admin_client):
    anonymous = app.test_client()
    assert anonymous.get("/admin/users").status_code == 302
    response = admin_client.get("/admin/users")
    assert response.status_code == 200
    assert "User administration" in response.get_data(as_text=True)


def test_unknown_page_renders_html_error(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404
    assert response.headers["Content-Type"].startswith("text/html")
    assert "could not be found" in response.get_data(as_text=True).lower()


def test_unknown_api_endpoint_returns_json(auth_client):
    response = auth_client.get("/api/this-does-not-exist")
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["error"]["code"] == "not_found"


def test_logout_page_never_logs_out_via_get(auth_client):
    response = auth_client.get("/logout")
    assert response.status_code == 302
    assert auth_client.get("/api/auth/me").status_code == 200


def test_pages_send_security_headers(client):
    response = client.get("/login")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
