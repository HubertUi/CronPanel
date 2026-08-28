"""Tests for the authentication endpoints."""


def test_login_success_returns_token(client, seeded_db, login_payload):
    response = client.post("/api/auth/login", data=login_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


def test_login_wrong_password_rejected_with_generic_error(client, seeded_db, admin_account):
    response = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": "totally-wrong"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


def test_login_unknown_user_same_error_as_wrong_password(client, seeded_db, admin_account):
    unknown_response = client.post(
        "/api/auth/login",
        data={"username": "ghost-user", "password": "whatever-pass"},
    )
    wrong_password_response = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": "totally-wrong"},
    )

    assert unknown_response.status_code == wrong_password_response.status_code == 401
    assert unknown_response.json() == wrong_password_response.json()


def test_login_updates_last_login(client, seeded_db, login_payload, auth_headers):
    client.post("/api/auth/login", data=login_payload)

    me = client.get("/api/auth/me", headers=auth_headers).json()
    assert me["last_login_at"] is not None


def test_me_requires_token(client, seeded_db):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"] in {"NOT_AUTHENTICATED", "UNAUTHORIZED"}


def test_me_returns_current_user_with_permissions(client, seeded_db, auth_headers, admin_account):
    response = client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == admin_account["username"]
    assert body["email"] == admin_account["email"]
    assert body["role"] == "admin"
    assert "tasks.read" in body["permissions"]


def test_me_rejects_tampered_token(client, seeded_db, auth_headers):
    tampered = auth_headers["Authorization"].replace("Bearer ", "")[:-2] + "xx"

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})

    assert response.status_code == 401


def test_logout_requires_authentication(client, seeded_db):
    response = client.post("/api/auth/logout")

    assert response.status_code == 401


def test_logout_with_valid_session(client, seeded_db, auth_headers):
    response = client.post("/api/auth/logout", headers=auth_headers)

    assert response.status_code == 200
    assert "message" in response.json()


def test_revoked_token_rejected_after_logout(client, seeded_db, login_payload):
    login = client.post("/api/auth/login", data=login_payload)
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/auth/logout", headers=headers)

    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401


def test_other_session_survives_single_logout(client, seeded_db, login_payload):
    token_a = client.post("/api/auth/login", data=login_payload).json()["access_token"]
    token_b = client.post("/api/auth/login", data=login_payload).json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    client.post("/api/auth/logout", headers=headers_a)

    assert client.get("/api/auth/me", headers=headers_b).status_code == 200
    assert client.get("/api/auth/me", headers=headers_a).status_code == 401
