"""Tests for the change-password endpoint."""


def test_change_password_success(client, seeded_db, admin_account):
    login_payload = {
        "username": admin_account["username"],
        "password": admin_account["password"],
    }
    new_password = "Nuev0Pa$$w0rd"

    # Change password
    token = client.post("/api/auth/login", data=login_payload).json()["access_token"]
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": admin_account["password"], "new_password": new_password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "actualizada" in resp.json()["message"].lower()

    # Old token should be revoked
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 401

    # New password should work
    resp2 = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": new_password},
    )
    assert resp2.status_code == 200


def test_change_password_wrong_current(client, seeded_db, admin_account):
    token = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": admin_account["password"]},
    ).json()["access_token"]

    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-current!", "new_password": "Nuev0Pa$$w0rd"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_CURRENT_PASSWORD"


def test_change_password_weak_new(client, seeded_db, admin_account):
    token = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": admin_account["password"]},
    ).json()["access_token"]

    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": admin_account["password"], "new_password": "weak"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "WEAK_PASSWORD"
    assert len(resp.json()["details"]) > 0


def test_change_password_requires_auth(client, seeded_db):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "any", "new_password": "any"},
    )
    assert resp.status_code == 401
