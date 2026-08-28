"""Tests for the audit trail (querying the audit_logs table directly)."""

from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.core import audit_actions as AuditAction


def test_login_success_audited(client, seeded_db, admin_account, db_session):
    client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": admin_account["password"]},
    )

    rows = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.LOGIN_SUCCESS).all()
    assert len(rows) >= 1
    latest = rows[-1]
    assert latest.user_id is not None
    assert latest.ip_address is not None


def test_login_failed_audited(client, seeded_db, admin_account, db_session):
    client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": "wrong"},
    )

    rows = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.LOGIN_FAILED).all()
    assert len(rows) >= 1
    # Ensure the failed-login details do NOT contain the attempted password.
    import json
    for row in rows:
        if row.details:
            assert "wrong" not in row.details.lower()


def test_logout_audited(client, seeded_db, admin_account, db_session):
    token = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": admin_account["password"]},
    ).json()["access_token"]
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    rows = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.LOGOUT).all()
    assert len(rows) >= 1


def test_password_change_audited(client, seeded_db, admin_account, db_session):
    new_pw = "Ch4ng3dP@ssw0rd"
    token = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": admin_account["password"]},
    ).json()["access_token"]
    client.post(
        "/api/auth/change-password",
        json={"current_password": admin_account["password"], "new_password": new_pw},
        headers={"Authorization": f"Bearer {token}"},
    )

    rows = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.PASSWORD_CHANGE).all()
    assert len(rows) >= 1
    # Ensure details do NOT contain the new password.
    import json
    for row in rows:
        if row.details:
            assert "ch4ng3d" not in row.details.lower()


def test_user_create_and_delete_audited(client, seeded_db, auth_headers, db_session):
    create_resp = client.post(
        "/api/users",
        json={
            "username": "audit_target",
            "email": "audit@test.local",
            "password": "Aud1tT@rg3t!",
            "role": "viewer",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    client.delete(f"/api/users/{user_id}", headers=auth_headers)

    creates = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.USER_CREATE).all()
    deletes = db_session.query(AuditLog).filter(AuditLog.action == AuditAction.USER_DELETE).all()
    assert len(creates) >= 1
    assert len(deletes) >= 1


def test_audit_never_contains_passwords(client, seeded_db, admin_account, db_session):
    password = admin_account["password"]
    token = client.post(
        "/api/auth/login",
        data={"username": admin_account["username"], "password": password},
    ).json()["access_token"]

    all_entries = db_session.query(AuditLog).all()
    for entry in all_entries:
        assert password.lower() not in (entry.details or "").lower(), (
            f"Audit entry {entry.id} leaks password in details"
        )
