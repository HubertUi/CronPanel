"""Phase 4: script allow-list API tests (admin CRUD + policy enforcement)."""

import os
import sys
from pathlib import Path

import pytest

from app.core import audit_actions as AuditAction
from app.models.audit_log import AuditLog
from app.models.script import Script

HELLO_SOURCE = "print('hola desde el script')"
FAIL_SOURCE = "import sys; sys.stderr.write('boom'); sys.exit(42)"
SLEEP_SOURCE = "import time; time.sleep(30); print('late')"
NOOP_SOURCE = "print('noop')"


def _write(parent: Path, filename: str, content: str = HELLO_SOURCE) -> Path:
    path = parent / filename
    path.write_text(content, encoding="utf-8")
    return path


def _register(client, headers, name: str, path: str | Path, **overrides):
    payload = {"name": name, "path": str(path), **overrides}
    return client.post("/api/scripts", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# Creation / policy
# ---------------------------------------------------------------------------

def test_register_script_within_allowlist(client, seeded_db, auth_headers, isolated_allowlist, db_session):
    script_path = _write(isolated_allowlist, "hello.py")
    resp = _register(client, auth_headers, "hello", script_path)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "hello"
    assert body["path"] == str(script_path)
    assert body["is_enabled"] is True
    assert body["created_by_username"] == "admin_test"

    stored = db_session.get(Script, body["id"])
    assert stored is not None
    assert stored.path == str(script_path)


def test_register_script_rejects_relative_path(client, seeded_db, auth_headers, isolated_allowlist):
    resp = _register(client, auth_headers, "rel", "scripts/hello.py")
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_PATH_NOT_ABSOLUTE"


def test_register_script_rejects_path_outside_allowlist(client, seeded_db, auth_headers, isolated_allowlist, tmp_path):
    outside = _write(tmp_path.parents[0], "evil.py")
    resp = _register(client, auth_headers, "evil", outside)
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_PATH_OUTSIDE_ALLOWLIST"


def test_register_script_rejects_missing_file(client, seeded_db, auth_headers, isolated_allowlist):
    missing = isolated_allowlist / "does_not_exist.py"
    resp = _register(client, auth_headers, "missing", missing)
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_FILE_MISSING"


def test_register_script_rejects_duplicate_name(client, seeded_db, auth_headers, isolated_allowlist):
    first = _write(isolated_allowlist, "dupe.py")
    assert _register(client, auth_headers, "dupe", first).status_code == 201
    second = _write(isolated_allowlist, "dupe2.py")
    resp = _register(client, auth_headers, "dupe", second)
    assert resp.status_code == 409
    assert resp.json()["error"] == "SCRIPT_NAME_CONFLICT"


def test_register_script_requires_admin_permission(client, seeded_db, operator_headers, viewer_headers, isolated_allowlist):
    script_path = _write(isolated_allowlist, "noperm.py")
    assert _register(client, operator_headers, "opter", script_path).status_code == 403
    assert _register(client, viewer_headers, "view", script_path).status_code == 403


def test_register_script_symlink_escaping_rejected(client, seeded_db, auth_headers, isolated_allowlist, tmp_path):
    """A symlink inside the allow-list must not escape to a file outside."""
    outside = tmp_path.parents[0] / "target_evil.py"
    outside.write_text("print('pwn')", encoding="utf-8")
    link = isolated_allowlist / "link.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported on this platform / permissions.")
    resp = _register(client, auth_headers, "link", link)
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_PATH_OUTSIDE_ALLOWLIST"


def test_register_script_audit_written(client, seeded_db, auth_headers, isolated_allowlist, db_session):
    script_path = _write(isolated_allowlist, "audited.py")
    resp = _register(client, auth_headers, "audited", script_path)
    assert resp.status_code == 201
    event = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.SCRIPT_CREATED)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert event is not None
    assert event.resource == "script"
    assert "audited" in (event.details or "")
    assert "password" not in (event.details or "").lower()


# ---------------------------------------------------------------------------
# Read / update / delete
# ---------------------------------------------------------------------------

def test_list_and_get_scripts_visible_to_all_roles(client, seeded_db, auth_headers, operator_headers, viewer_headers, isolated_allowlist):
    script_path = _write(isolated_allowlist, "shared.py")
    created = _register(client, auth_headers, "shared", script_path).json()
    script_id = created["id"]

    for headers in (operator_headers, viewer_headers):
        listing = client.get("/api/scripts", headers=headers)
        assert listing.status_code == 200
        assert any(entry["id"] == script_id for entry in listing.json())
        single = client.get(f"/api/scripts/{script_id}", headers=headers)
        assert single.status_code == 200
        assert single.json()["name"] == "shared"


def test_update_script_fields_by_admin(client, seeded_db, auth_headers, isolated_allowlist, db_session):
    script_path = _write(isolated_allowlist, "update_me.py")
    script_id = _register(client, auth_headers, "update_me", script_path).json()["id"]

    resp = client.put(
        f"/api/scripts/{script_id}",
        json={"name": "update_me_2", "description": "nueva desc"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "update_me_2"
    assert body["description"] == "nueva desc"

    event = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.SCRIPT_UPDATED)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert event is not None
    assert "name" in (event.details or "")


def test_update_script_disable_audits_toggle(client, seeded_db, auth_headers, isolated_allowlist, db_session):
    script_path = _write(isolated_allowlist, "toggle.py")
    script_id = _register(client, auth_headers, "toggle", script_path).json()["id"]

    resp = client.put(f"/api/scripts/{script_id}", json={"is_enabled": False}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_enabled"] is False

    event = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == AuditAction.SCRIPT_DISABLED)
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert event is not None


def test_update_script_rejects_path_outside_allowlist(client, seeded_db, auth_headers, isolated_allowlist, tmp_path):
    script_path = _write(isolated_allowlist, "move_me.py")
    script_id = _register(client, auth_headers, "move_me", script_path).json()["id"]
    outside = tmp_path.parents[0] / "escape.py"
    outside.write_text("print('x')", encoding="utf-8")
    resp = client.put(f"/api/scripts/{script_id}", json={"path": str(outside)}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["error"] == "SCRIPT_PATH_OUTSIDE_ALLOWLIST"


def test_update_script_requires_admin(client, seeded_db, auth_headers, operator_headers, isolated_allowlist):
    script_path = _write(isolated_allowlist, "noedit.py")
    script_id = _register(client, auth_headers, "noedit", script_path).json()["id"]
    resp = client.put(f"/api/scripts/{script_id}", json={"name": "hacked"}, headers=operator_headers)
    assert resp.status_code == 403


def test_delete_script_in_use_blocked(client, seeded_db, auth_headers, operator_headers, isolated_allowlist):
    script_path = _write(isolated_allowlist, "busy.py")
    script_id = _register(client, auth_headers, "busy", script_path).json()["id"]

    job = client.post(
        "/api/cron-jobs",
        json={
            "name": "job con script",
            "command": "/ruta/placeholder.sh",
            "schedule_expression": "0 2 * * *",
            "script_id": script_id,
        },
        headers=auth_headers,
    )
    assert job.status_code == 201, job.text

    resp = client.delete(f"/api/scripts/{script_id}", headers=auth_headers)
    assert resp.status_code == 409
    assert resp.json()["error"] == "SCRIPT_IN_USE"


def test_delete_script_soft_deletes_and_hides(client, seeded_db, auth_headers, isolated_allowlist):
    script_path = _write(isolated_allowlist, "gone.py")
    script_id = _register(client, auth_headers, "gone", script_path).json()["id"]

    assert client.delete(f"/api/scripts/{script_id}", headers=auth_headers).status_code == 204
    listing = client.get("/api/scripts", headers=auth_headers).json()
    assert all(entry["id"] != script_id for entry in listing)
    assert client.get(f"/api/scripts/{script_id}", headers=auth_headers).status_code == 404