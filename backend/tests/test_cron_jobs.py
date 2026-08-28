"""End-to-end tests for the CronJob API (Phase 3).

Covers CRUD, RBAC, per-owner access control, audit trail, per-job history and
the explicit guarantee that Phase 3 NEVER executes the stored `command`.
"""

import json

from app.core import audit_actions as AuditAction
from app.core import cron_history_actions as HistoryAction
from app.models.audit_log import AuditLog
from app.models.cron_job import CronJob
from app.models.cron_job_history import CronJobHistory

JOB_PAYLOAD = {
    "name": "Backup diario",
    "description": "Programación del backup",
    "command": "/ruta/placeholder/script.sh",
    "schedule_expression": "0 2 * * *",
}


def _create(client, headers, **overrides):
    payload = {**JOB_PAYLOAD, **overrides}
    return client.post("/api/cron-jobs", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

def test_create_job_stores_data_without_executing(client, seeded_db, auth_headers, db_session):
    resp = _create(client, auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] >= 1
    assert body["name"] == "Backup diario"
    assert body["command"] == "/ruta/placeholder/script.sh"
    assert body["schedule_expression"] == "0 2 * * *"
    assert body["minute"] == "0"
    assert body["hour"] == "2"
    assert body["day_of_month"] == "*"
    assert body["month"] == "*"
    assert body["day_of_week"] == "*"
    assert body["human_description"] == "Todos los días a las 02:00"
    assert body["is_active"] is True
    assert body["owner_id"] is not None
    assert "schedule" not in body  # internal naming not exposed

    stored = db_session.get(CronJob, body["id"])
    assert stored is not None
    assert stored.command == "/ruta/placeholder/script.sh"


def test_create_job_normalizes_expression(client, seeded_db, auth_headers):
    resp = _create(client, auth_headers, schedule_expression="  0   2 * * 7 ")
    assert resp.status_code == 201
    assert resp.json()["schedule_expression"] == "0 2 * * 0"
    assert resp.json()["day_of_week"] == "0"


def test_create_job_invalid_expression_rejected(client, seeded_db, auth_headers):
    resp = _create(client, auth_headers, schedule_expression="61 * * * *")
    assert resp.status_code == 422
    assert resp.json()["error"] == "VALIDATION_ERROR"


def test_create_job_requires_permission(client, seeded_db, viewer_headers):
    resp = _create(client, viewer_headers)
    assert resp.status_code == 403


def test_create_job_requires_authentication(client, seeded_db):
    resp = _create(client, {})
    assert resp.status_code == 401


def test_create_job_rejects_oversized_command(client, seeded_db, auth_headers):
    resp = _create(client, auth_headers, command="x" * 2001)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Listing and reading
# ---------------------------------------------------------------------------

def test_admin_sees_all_jobs(client, seeded_db, auth_headers, operator_headers):
    _create(client, auth_headers, name="Job admin")
    _create(client, operator_headers, name="Job operator")

    resp = client.get("/api/cron-jobs", headers=auth_headers)
    assert resp.status_code == 200
    names = {job["name"] for job in resp.json()}
    assert {"Job admin", "Job operator"} <= names


def test_operator_only_sees_own_jobs(client, seeded_db, auth_headers, operator_headers):
    _create(client, auth_headers, name="Job admin")
    _create(client, operator_headers, name="Job operator")

    resp = client.get("/api/cron-jobs", headers=operator_headers)
    assert resp.status_code == 200
    names = {job["name"] for job in resp.json()}
    assert names == {"Job operator"}


def test_list_filters_active_and_name(client, seeded_db, auth_headers):
    created = _create(client, auth_headers, name="Backup mysql")
    _create(client, auth_headers, name="Backup logs")

    job_id = created.json()["id"]
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)

    active = client.get("/api/cron-jobs?active=true", headers=auth_headers).json()
    assert all(job["is_active"] for job in active)

    filtered = client.get("/api/cron-jobs?name=mysql", headers=auth_headers).json()
    assert len(filtered) == 1
    assert filtered[0]["name"] == "Backup mysql"


def test_get_job_by_id(client, seeded_db, auth_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.get(f"/api/cron-jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


def test_get_unknown_job_returns_404(client, seeded_db, auth_headers):
    resp = client.get("/api/cron-jobs/9999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"] == "CRON_JOB_NOT_FOUND"


def test_other_user_cannot_see_job(client, seeded_db, auth_headers, operator_headers):
    job_id = _create(client, auth_headers, name="Privado").json()["id"]
    resp = client.get(f"/api/cron-jobs/{job_id}", headers=operator_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Ownership and RBAC on mutations
# ---------------------------------------------------------------------------

def test_another_operator_cannot_update_job(client, seeded_db, auth_headers, operator_headers):
    job_id = _create(client, operator_headers, name="Job A").json()["id"]
    other = _create(client, operator_headers, name="Job B").json()["id"]

    # A second operator cannot touch A, but can touch their own job B.
    second_operator = client.post(
        "/api/users",
        json={
            "username": "operator_2",
            "email": "operator2@test.local",
            "password": "Operador2!Pass",
            "role": "operator",
        },
        headers=auth_headers,
    ).json()["id"]
    second_headers = None
    login = client.post(
        "/api/auth/login",
        data={"username": "operator_2", "password": "Operador2!Pass"},
    )
    second_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert second_operator >= 1
    resp = client.put(
        f"/api/cron-jobs/{job_id}",
        json={"name": "A modificada"},
        headers=second_headers,
    )
    assert resp.status_code == 403

    resp = client.put(
        f"/api/cron-jobs/{other}",
        json={"name": "B modificada"},
        headers=second_headers,
    )
    assert resp.status_code == 403  # B belongs to the first operator, not to the second one


def test_admin_can_update_any_job(client, seeded_db, auth_headers, operator_headers):
    job_id = _create(client, operator_headers).json()["id"]
    resp = client.put(
        f"/api/cron-jobs/{job_id}",
        json={"name": "Renombrado por admin"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renombrado por admin"


def test_update_validates_expression_again(client, seeded_db, auth_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.put(
        f"/api/cron-jobs/{job_id}",
        json={"schedule_expression": "not-a-cron"},
        headers=auth_headers,
    )
    assert resp.status_code == 422

    before = client.get(f"/api/cron-jobs/{job_id}", headers=auth_headers).json()
    assert before["schedule_expression"] == "0 2 * * *"


def test_update_with_no_changes_is_noop(client, seeded_db, auth_headers):
    created = _create(client, auth_headers, name="Estable")
    job_id = created.json()["id"]
    resp = client.put(
        f"/api/cron-jobs/{job_id}",
        json={"name": "Estable"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    history = client.get(f"/api/cron-jobs/{job_id}/history", headers=auth_headers).json()
    assert [item["action"] for item in history] == [HistoryAction.CREATED]


def test_status_enable_disable(client, seeded_db, auth_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": True}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_status_change_denied_for_non_owner(client, seeded_db, auth_headers, operator_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=operator_headers)
    assert resp.status_code == 403


def test_viewer_cannot_change_status(client, seeded_db, auth_headers, viewer_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=viewer_headers)
    assert resp.status_code == 403


def test_operator_cannot_delete_even_own_job(client, seeded_db, operator_headers):
    """'cron_jobs.delete' is reserved for the admin role."""
    job_id = _create(client, operator_headers).json()["id"]
    resp = client.delete(f"/api/cron-jobs/{job_id}", headers=operator_headers)
    assert resp.status_code == 403


def test_admin_can_delete_job(client, seeded_db, auth_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 204

    assert client.get(f"/api/cron-jobs/{job_id}", headers=auth_headers).status_code == 404
    listed = client.get("/api/cron-jobs", headers=auth_headers).json()
    assert all(job["id"] != job_id for job in listed)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def test_history_records_all_actions(client, seeded_db, auth_headers):
    job_id = _create(client, auth_headers).json()["id"]
    client.put(f"/api/cron-jobs/{job_id}", json={"description": "Nueva desc."}, headers=auth_headers)
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": True}, headers=auth_headers)
    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)

    history = client.get(f"/api/cron-jobs/{job_id}/history", headers=auth_headers).json()
    actions = [item["action"] for item in history]
    assert actions == [
        HistoryAction.CREATED,
        HistoryAction.UPDATED,
        HistoryAction.DISABLED,
        HistoryAction.ENABLED,
        HistoryAction.DELETED,
    ]

    updated_entry = next(item for item in history if item["action"] == HistoryAction.UPDATED)
    assert updated_entry["changes"]["description"] == {"from": "Programación del backup", "to": "Nueva desc."}
    assert updated_entry["username"] is not None


def test_history_persists_after_delete(client, seeded_db, auth_headers, db_session):
    job_id = _create(client, auth_headers).json()["id"]
    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)

    rows = db_session.query(CronJobHistory).filter(CronJobHistory.cron_job_id == job_id).all()
    assert [row.action for row in rows] == [HistoryAction.CREATED, HistoryAction.DELETED]


def test_history_denied_for_non_owner(client, seeded_db, auth_headers, operator_headers):
    job_id = _create(client, auth_headers).json()["id"]
    resp = client.get(f"/api/cron-jobs/{job_id}/history", headers=operator_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_audit_records_cron_job_actions(client, seeded_db, auth_headers, db_session):
    job_id = _create(client, auth_headers).json()["id"]
    client.put(f"/api/cron-jobs/{job_id}", json={"name": "Audit rename"}, headers=auth_headers)
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)

    def _count(action):
        return db_session.query(AuditLog).filter(
            AuditLog.action == action,
            AuditLog.resource == "cron_job",
            AuditLog.resource_id == str(job_id),
        ).count()

    assert _count(AuditAction.CRON_JOB_CREATED) == 1
    assert _count(AuditAction.CRON_JOB_UPDATED) == 1
    assert _count(AuditAction.CRON_JOB_DISABLED) == 1
    assert _count(AuditAction.CRON_JOB_DELETED) == 1


def test_audit_enabled_action(client, seeded_db, auth_headers, db_session):
    job_id = _create(client, auth_headers).json()["id"]
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": True}, headers=auth_headers)

    count = db_session.query(AuditLog).filter(
        AuditLog.action == AuditAction.CRON_JOB_ENABLED,
        AuditLog.resource_id == str(job_id),
    ).count()
    assert count == 1


def test_audit_never_contains_commands_or_secrets(client, seeded_db, auth_headers, db_session):
    """Global audit details must not embed the full command definition."""
    resp = _create(client, auth_headers, command="echo s3cr3t-token-xyz")
    assert resp.status_code == 201

    entries = db_session.query(AuditLog).filter(
        AuditLog.action == AuditAction.CRON_JOB_CREATED
    ).all()
    for entry in entries:
        assert "s3cr3t-token-xyz" not in (entry.details or "")


# ---------------------------------------------------------------------------
# Explicit no-execution guarantee
# ---------------------------------------------------------------------------

def test_crud_never_executes_commands(client, seeded_db, auth_headers, monkeypatch):
    """Phase 3 must only persist data.

    Execution primitives are replaced with probes: if any were invoked while
    performing the full CRUD cycle, the probe raises and the test fails.
    """

    import os
    import subprocess

    calls = []

    def _probe(name):
        def _probed(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"Prohibited execution primitive called: {name}")
        return _probed

    monkeypatch.setattr(subprocess, "run", _probe("subprocess.run"))
    monkeypatch.setattr(subprocess, "Popen", _probe("subprocess.Popen"))
    monkeypatch.setattr(os, "system", _probe("os.system"))
    monkeypatch.setattr(os, "popen", _probe("os.popen"))

    job_id = _create(client, auth_headers, command="rm -rf / && whoami").json()["id"]
    client.get(f"/api/cron-jobs/{job_id}", headers=auth_headers)
    client.put(
        f"/api/cron-jobs/{job_id}",
        json={"command": "comando cualquiera"},
        headers=auth_headers,
    )
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)

    assert calls == []


def test_cron_job_source_never_calls_execution_primitives():
    """Static scan: the Phase 3 code paths contain no execution primitives.

    Uses the AST so docstrings/comments that merely mention the word
    'crontab' (e.g. "never touches the crontab") are not false positives.
    """

    import ast
    from pathlib import Path

    BACKEND_DIR = Path(__file__).resolve().parents[1]
    forbidden_imports = {"subprocess"}
    forbidden_module_attrs = ("system", "popen", "run", "Popen", "call", "check_call", "check_output")
    forbidden_builtins = ("eval", "exec", "compile")

    targets = [
        BACKEND_DIR / "app" / "services" / "cron_job_service.py",
        BACKEND_DIR / "app" / "api" / "routes" / "cron_jobs.py",
        BACKEND_DIR / "app" / "repositories" / "cron_job_repository.py",
        BACKEND_DIR / "app" / "models" / "cron_job.py",
        BACKEND_DIR / "app" / "models" / "cron_job_history.py",
        BACKEND_DIR / "app" / "utils" / "cron_validator.py",
        BACKEND_DIR / "app" / "schemas" / "cron_job.py",
    ]
    for target in targets:
        source = target.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(target))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = {alias.name.split(".")[0] for alias in node.names}
                assert not (imported & forbidden_imports), f"{target.name} imports subprocess"

            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root not in forbidden_imports, f"{target.name} imports subprocess"

            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in forbidden_builtins:
                    raise AssertionError(f"{target.name} calls {func.id}()")
                if isinstance(func, ast.Attribute):
                    assert func.attr not in forbidden_module_attrs, (
                        f"{target.name} calls {func.attr}()"
                    )


def test_validate_endpoint_returns_struct(client, seeded_db, auth_headers):
    resp = client.post(
        "/api/cron-jobs/validate",
        json={"schedule_expression": "30 8 * * 1-5"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["normalized_expression"] == "30 8 * * 1-5"
    assert body["description"] == "Lunes a viernes a las 08:30"

    bad = client.post(
        "/api/cron-jobs/validate",
        json={"schedule_expression": "99 * * * *"},
        headers=auth_headers,
    )
    assert bad.status_code == 200
    assert bad.json()["valid"] is False
    assert bad.json()["error_code"] == "VALUE_OUT_OF_RANGE"