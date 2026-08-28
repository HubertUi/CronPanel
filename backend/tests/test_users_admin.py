"""Tests for the user administration endpoints."""


def test_admin_can_create_user(client, seeded_db, auth_headers):
    resp = client.post(
        "/api/users",
        json={
            "username": "new_user_01",
            "email": "new@test.local",
            "password": "N3wU5er!Pass",
            "role": "viewer",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "new_user_01"
    assert body["role"] == "viewer"
    assert "password" not in body and "hashed" not in body


def test_admin_cannot_create_duplicate_username(client, seeded_db, auth_headers, admin_account):
    client.post(
        "/api/users",
        json={
            "username": admin_account["username"],
            "email": "dup@test.local",
            "password": "D1ff3rentPass!",
            "role": "viewer",
        },
        headers=auth_headers,
    )
    resp = client.post(
        "/api/users",
        json={
            "username": admin_account["username"],
            "email": "dup2@test.local",
            "password": "D1ff3rentPass!",
            "role": "viewer",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "DUPLICATE_IDENTITY"


def test_admin_can_list_users(client, seeded_db, auth_headers):
    resp = client.get("/api/users", headers=auth_headers)
    assert resp.status_code == 200
    usernames = [u["username"] for u in resp.json()]
    assert "admin_test" in usernames
    assert "operator_test" in usernames


def test_admin_can_get_user_by_id(client, seeded_db, auth_headers):
    resp = client.get("/api/users/1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_non_admin_cannot_list_users(client, seeded_db, operator_headers):
    resp = client.get("/api/users", headers=operator_headers)
    assert resp.status_code == 403


def test_operator_can_view_tasks_but_not_users(client, seeded_db, operator_headers):
    assert client.get("/api/users", headers=operator_headers).status_code == 403


def test_admin_can_deactivate_user(client, seeded_db, auth_headers, viewer_account, viewer_headers):
    viewer = client.get(
        "/api/users", headers=auth_headers
    )
    viewer_id = [u["id"] for u in viewer.json() if u["username"] == viewer_account["username"]][0]

    resp = client.put(
        f"/api/users/{viewer_id}",
        json={"is_active": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    # Viewer's existing token should now be rejected
    me_resp = client.get("/api/auth/me", headers=viewer_headers)
    assert me_resp.status_code == 401

    # Viewer cannot login
    login_resp = client.post(
        "/api/auth/login",
        data={"username": viewer_account["username"], "password": viewer_account["password"]},
    )
    assert login_resp.status_code == 401


def test_last_admin_cannot_be_deleted(client, seeded_db, auth_headers, admin_account):
    resp = client.delete("/api/users/1", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"] == "LAST_ADMIN_PROTECTED"


def test_last_admin_cannot_be_deactivated(client, seeded_db, auth_headers):
    resp = client.put(
        "/api/users/1", json={"is_active": False}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_last_admin_cannot_be_demoted(client, seeded_db, auth_headers):
    resp = client.put(
        "/api/users/1", json={"role": "viewer"}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_admin_can_delete_non_admin_user(client, seeded_db, auth_headers, viewer_account):
    viewer = client.get("/api/users", headers=auth_headers)
    viewer_id = [u["id"] for u in viewer.json() if u["username"] == viewer_account["username"]][0]

    resp = client.delete(f"/api/users/{viewer_id}", headers=auth_headers)
    assert resp.status_code == 204

    assert client.get(f"/api/users/{viewer_id}", headers=auth_headers).status_code == 404


def test_two_admins_can_delete_one(client, seeded_db, auth_headers):
    resp = client.post(
        "/api/users",
        json={
            "username": "admin2",
            "email": "admin2@test.local",
            "password": "Adm1nPa$$w0rd",
            "role": "admin",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    admin2_id = resp.json()["id"]

    resp2 = client.delete(f"/api/users/{admin2_id}", headers=auth_headers)
    assert resp2.status_code == 204


def test_admin_can_activate_user(client, seeded_db, auth_headers, viewer_account):
    viewer = client.get("/api/users", headers=auth_headers)
    viewer_id = [u["id"] for u in viewer.json() if u["username"] == viewer_account["username"]][0]

    client.put(f"/api/users/{viewer_id}", json={"is_active": False}, headers=auth_headers)
    resp = client.put(f"/api/users/{viewer_id}", json={"is_active": True}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_admin_role_change_invalidates_old_tokens(
    client, seeded_db, auth_headers, operator_account
):
    op = client.get("/api/users", headers=auth_headers)
    op_id = [u["id"] for u in op.json() if u["username"] == operator_account["username"]][0]

    # Operator logs in and gets a token (role claim = "operator")
    op_token = client.post(
        "/api/auth/login",
        data={"username": operator_account["username"], "password": operator_account["password"]},
    ).json()["access_token"]
    op_headers = {"Authorization": f"Bearer {op_token}"}

    # Admin promotes operator to admin → role change invalidates old tokens
    resp = client.put(f"/api/users/{op_id}", json={"role": "admin"}, headers=auth_headers)
    assert resp.status_code == 200

    # Old token (with "operator" claim) is now stale
    me_resp = client.get("/api/auth/me", headers=op_headers)
    assert me_resp.status_code == 401
