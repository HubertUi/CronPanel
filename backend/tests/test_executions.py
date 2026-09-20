"""Phase 4: controlled execution engine tests.

Covers the pipeline policy (script required/enabled/inside allow-list, job
active, RBAC, ownership), the executor behaviour (exit codes, timeout, output
cap), persistence/audit of every run, and the static security contract.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import audit_actions as AuditAction
from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.execution import Execution

HI_SOURCE = "import sys; sys.stdout.write('hola desde el script'); sys.stderr.write(''); sys.exit(0)"
FAIL_SOURCE = "import sys; sys.stderr.write('boom'); sys.exit(42)"
SLEEP_SOURCE = "import time; time.sleep(30); print('late')"
NOISE_SOURCE = "import sys; sys.stdout.write('x' * 100000)"

JOB_PAYLOAD = {
    "name": "Tarea de ejecución",
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


def _audit_actions_for(db_session, action: str):
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.action == action)
        .order_by(AuditLog.id.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Execution outcomes
# ---------------------------------------------------------------------------

def test_execute_success_persists_output_and_audit(
    client, seeded_db, auth_headers, isolated_allowlist, db_session
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "hey", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "job-hi", script_id)

    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cron_job_id"] == job_id
    assert body["script_id"] == script_id
    assert body["script_name"] == "hey"
    assert body["status"] == "success"
    assert body["exit_code"] == 0
    assert "hola desde el script" in (body["stdout"] or "")
    assert body["duration_ms"] is not None
    assert body["trigger"] == "manual"
    assert body["username"] == "admin_test"
    assert body["finished_at"] is not None

    stored = db_session.get(Execution, body["id"])
    assert stored.status == "success"
    assert stored.stdout == body["stdout"]

    actions = {event.action for event in _audit_actions_for(db_session, AuditAction.EXECUTION_STARTED)}
    started = _audit_actions_for(db_session, AuditAction.EXECUTION_STARTED)[0]
    assert started.resource_id == str(body["id"])
    succeeded = _audit_actions_for(db_session, AuditAction.EXECUTION_SUCCEEDED)
    assert succeeded and succeeded[0].resource_id == str(body["id"])


def test_execute_nonzero_exit_marked_failed(
    client, seeded_db, auth_headers, isolated_allowlist
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "fail", FAIL_SOURCE)
    job_id = _make_job(client, auth_headers, "job-fail", script_id)

    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["exit_code"] == 42
    assert "boom" in (body["stderr"] or "")


def test_execute_timeout_kills_and_marks_timed_out(
    client, seeded_db, auth_headers, isolated_allowlist, monkeypatch
):
    monkeypatch.setattr(settings, "EXECUTION_TIMEOUT_SECONDS", 1)
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "sleeper", SLEEP_SOURCE)
    job_id = _make_job(client, auth_headers, "job-sleeper", script_id)

    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "timed_out"
    assert body["error"] == "timeout_expired"
    assert body["finished_at"] is not None


def test_execute_output_is_capped(client, seeded_db, auth_headers, isolated_allowlist, monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_OUTPUT_MAX_CHARS", 1024)
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "noisy", NOISE_SOURCE)
    job_id = _make_job(client, auth_headers, "job-noisy", script_id)

    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["stdout"] or "") <= 1024
    assert "[output truncated]" in body["stdout"]


# ---------------------------------------------------------------------------
# Policy pre-flight rejections
# ---------------------------------------------------------------------------

def test_execute_rejects_job_without_script(client, seeded_db, auth_headers, isolated_allowlist):
    job_id = _make_job(client, auth_headers, "job-noscript")
    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_REQUIRED"


def test_execute_rejects_disabled_script(client, seeded_db, auth_headers, isolated_allowlist):
    _, script_id = _make_script(
        client, auth_headers, isolated_allowlist, "disabled", HI_SOURCE, enabled=False
    )
    job_id = _make_job(client, auth_headers, "job-disabled", script_id)
    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_UNAVAILABLE"


def test_execute_rejects_inactive_job(client, seeded_db, auth_headers, isolated_allowlist):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "inactive", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "job-inactive", script_id)
    resp = client.patch(f"/api/cron-jobs/{job_id}/status", json={"is_active": False}, headers=auth_headers)
    assert resp.status_code == 200

    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"] == "JOB_INACTIVE"


def test_execute_rejects_deleted_job(client, seeded_db, auth_headers, isolated_allowlist):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "deleted", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "job-deleted", script_id)
    client.delete(f"/api/cron-jobs/{job_id}", headers=auth_headers)
    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["error"] == "CRON_JOB_NOT_FOUND"


# ---------------------------------------------------------------------------
# RBAC / ownership on execution
# ---------------------------------------------------------------------------

def test_execute_requires_execute_permission(client, seeded_db, auth_headers, viewer_headers, isolated_allowlist):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "perm", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "job-perm", script_id)
    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=viewer_headers)
    assert resp.status_code == 403


def test_execute_requires_ownership(client, seeded_db, auth_headers, operator_headers, isolated_allowlist):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "own", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "job-own", script_id)
    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=operator_headers)
    assert resp.status_code == 403
    assert resp.json()["error"] == "CRON_JOB_FORBIDDEN"


# ---------------------------------------------------------------------------
# No arbitrary command execution
# ---------------------------------------------------------------------------

def test_execute_uses_only_registered_script_path(
    client, seeded_db, auth_headers, isolated_allowlist, monkeypatch, db_session
):
    """The free-form `command` field must never influence the launched argv."""
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "isolated", HI_SOURCE)
    script_path = isolated_allowlist / "isolated.py"
    job_id = _make_job(
        client,
        auth_headers,
        "job-isolated",
        script_id,
        command="ping evil.example && cat /etc/passwd || rm -rf /",
    )

    calls = []

    class _FakeResult:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = b"ok\n"
            self.stderr = b""

    def _spy(args, *spy_extra, **kwargs):
        calls.append((list(args), kwargs))
        return _FakeResult()

    monkeypatch.setattr(subprocess, "run", _spy)

    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == [sys.executable, str(script_path)]
    assert kwargs.get("shell") is not True
    assert all("ping" not in arg and "passwd" not in arg and "rm " not in arg for arg in argv)

    details = " ".join(
        (event.details or "") for event in _audit_actions_for(db_session, AuditAction.EXECUTION_STARTED)
    )
    assert "ping" not in details
    assert "passwd" not in details


# ---------------------------------------------------------------------------
# History listing / reading
# ---------------------------------------------------------------------------

def test_executions_scoped_by_ownership(
    client, seeded_db, auth_headers, operator_headers, viewer_headers, isolated_allowlist
):
    _, admin_script = _make_script(client, auth_headers, isolated_allowlist, "aa1", HI_SOURCE)
    admin_job = _make_job(client, auth_headers, "admin-job", admin_script)
    client.post(f"/api/cron-jobs/{admin_job}/execute", headers=auth_headers)

    _, op_script = _make_script(client, auth_headers, isolated_allowlist, "oo1", HI_SOURCE)
    op_job = _make_job(client, operator_headers, "operator-job", op_script)
    client.post(f"/api/cron-jobs/{op_job}/execute", headers=operator_headers)

    admin_rows = client.get("/api/executions", headers=auth_headers).json()
    op_rows = client.get("/api/executions", headers=operator_headers).json()
    viewer_rows = client.get("/api/executions", headers=viewer_headers).json()

    assert len(admin_rows) == 2
    assert len(op_rows) == 1
    assert op_rows[0]["cron_job_id"] == op_job
    assert op_rows[0]["script_name"] == "oo1"
    assert viewer_rows == []


def test_get_execution_of_others_returns_404(
    client, seeded_db, auth_headers, operator_headers, isolated_allowlist
):
    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "priv", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "priv-job", script_id)
    exec_id = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers).json()["id"]

    resp = client.get(f"/api/executions/{exec_id}", headers=operator_headers)
    assert resp.status_code == 404
    assert resp.json()["error"] == "EXECUTION_NOT_FOUND"

    assert client.get(f"/api/executions/{exec_id}", headers=auth_headers).status_code == 200


def test_list_executions_filter_by_status_and_job(
    client, seeded_db, auth_headers, operator_headers, isolated_allowlist
):
    _, s1 = _make_script(client, auth_headers, isolated_allowlist, "f-s1", HI_SOURCE)
    j1 = _make_job(client, auth_headers, "f-j1", s1)
    client.post(f"/api/cron-jobs/{j1}/execute", headers=auth_headers)

    _, s2 = _make_script(client, auth_headers, isolated_allowlist, "f-s2", FAIL_SOURCE)
    j2 = _make_job(client, auth_headers, "f-j2", s2)
    client.post(f"/api/cron-jobs/{j2}/execute", headers=auth_headers)

    only_j1 = client.get("/api/executions", params={"job_id": j1}, headers=auth_headers).json()
    assert len(only_j1) == 1
    assert only_j1[0]["cron_job_id"] == j1

    failed = client.get("/api/executions", params={"status": "failed"}, headers=auth_headers).json()
    assert len(failed) == 1
    assert failed[0]["cron_job_id"] == j2


# ---------------------------------------------------------------------------
# Static security contract (Phase 4)
# ---------------------------------------------------------------------------

PHASE4_NO_SUBPROCESS = [
    "app/core/execution_status.py",
    "app/execution/policy.py",
    "app/services/script_service.py",
    "app/services/execution_service.py",
    "app/api/routes/scripts.py",
    "app/api/routes/executions.py",
    "app/api/routes/cron_jobs.py",
    "app/repositories/execution_repository.py",
    "app/models/script.py",
    "app/models/execution.py",
    "app/models/cron_job.py",
    "app/schemas/script.py",
    "app/schemas/execution.py",
    "app/schemas/cron_job.py",
]

# Docstrings legitimately *describe* the security contract; these files are
# therefore scanned via AST only (no raw-text word checks).
PHASE4_AST_ONLY = ["app/execution/__init__.py"]


def _parse_tree(relative: Path, backend_dir: Path) -> tuple[Path, ast.Module]:
    target = backend_dir / relative
    tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    return target, tree


def test_execution_source_security_contract():
    """Only `executor.py` may import subprocess; nothing may call shell/os
    primitives or eval/exec; the crontab is never touched."""
    BACKEND_DIR = Path(__file__).resolve().parents[1]
    forbidden_attrs = ("system", "popen", "call", "check_call", "check_output", "Popen")
    forbidden_builtins = ("eval", "exec", "compile")

    executor = BACKEND_DIR / "app" / "execution" / "executor.py"
    source = executor.read_text(encoding="utf-8")
    assert "import subprocess" in source

    for relative in PHASE4_NO_SUBPROCESS + PHASE4_AST_ONLY + ["app/execution/executor.py"]:
        target, tree = _parse_tree(relative, BACKEND_DIR)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])

        if relative == "app/execution/executor.py":
            assert "subprocess" in imported_roots, "executor must import subprocess"
        else:
            assert "subprocess" not in imported_roots, f"{relative} imports subprocess"

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if any(
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and bool(kw.value.value)
                    for kw in node.keywords
                ):
                    raise AssertionError(f"{relative} enables shell=true")
                func = node.func
                if isinstance(func, ast.Name) and func.id in forbidden_builtins:
                    raise AssertionError(f"{relative} calls {func.id}()")
                if isinstance(func, ast.Attribute):
                    assert func.attr not in forbidden_attrs, (
                        f"{relative} calls {func.attr}()"
                    )

    for relative in PHASE4_NO_SUBPROCESS:
        target = BACKEND_DIR / relative
        text = target.read_text(encoding="utf-8")
        assert "os.system" not in text
        assert "os.popen" not in text
        assert "eval(" not in text
        assert "exec(" not in text
        assert "/etc/cron" not in text
        assert "/var/spool/cron" not in text


def test_crontab_never_touched_runtime(client, seeded_db, auth_headers, isolated_allowlist, monkeypatch, tmp_path):
    """Executing a job must never write to the system crontab."""
    import builtins

    from app.execution import executor as executor_module

    opened = []
    original_open = builtins.open

    def spy_open(*args, **kwargs):
        opened.append(args[0])
        return original_open(*args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)

    _, script_id = _make_script(client, auth_headers, isolated_allowlist, "cronev", HI_SOURCE)
    job_id = _make_job(client, auth_headers, "cronev-job", script_id)
    resp = client.post(f"/api/cron-jobs/{job_id}/execute", headers=auth_headers)
    assert resp.status_code == 200

    evil_targets = ("/etc/crontab", "/etc/cron.d", "/var/spool/cron", "/etc/anacrontab")
    assert not any("/etc/cron" in str(path).lower() or "spool/cron" in str(path).lower() for path in opened)