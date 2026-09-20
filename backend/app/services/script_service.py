"""Script business logic: allow-list registration and lifecycle.

Scripts represent *files*, not command strings. Only administrators reach this
service (the routes enforce ``SCRIPTS_CREATE`` / ``UPDATE`` / ``DELETE``); the
execution policy validates every stored path against the allow-list root.
"""

from sqlalchemy.orm import Session

from app.core import audit_actions as AuditAction
from app.execution.policy import canonicalize_script_path
from app.models.script import Script
from app.models.user import User
from app.repositories.execution_repository import ScriptRepository
from app.services import audit_service


class ScriptNotFoundError(Exception):
    pass


class ScriptNameConflictError(Exception):
    pass


class ScriptInUseError(Exception):
    pass


def _get_script(session: Session, script_id: int) -> Script:
    script = ScriptRepository(session).get_by_id(script_id)
    if script is None:
        raise ScriptNotFoundError
    return script


def create_script(
    session: Session,
    actor: User,
    *,
    name: str,
    description: str | None,
    path: str,
    ip_address: str | None = None,
) -> Script:
    validated = canonicalize_script_path(path)

    existing = ScriptRepository(session).get_by_name(name)
    if existing is not None:
        raise ScriptNameConflictError

    script = Script(
        name=name,
        description=description,
        path=str(validated.path),
        is_enabled=True,
        created_by=actor.id,
    )
    ScriptRepository(session).add(script, commit=False)
    audit_service.record_event(
        session,
        AuditAction.SCRIPT_CREATED,
        user_id=actor.id,
        username=actor.username,
        resource="script",
        resource_id=str(script.id),
        ip_address=ip_address,
        details={"name": script.name, "path": script.path},
        commit=True,
    )
    return script


def list_scripts(session: Session) -> list[Script]:
    return ScriptRepository(session).list_scripts()


def get_script(session: Session, script_id: int) -> Script:
    return _get_script(session, script_id)


def update_script(
    session: Session,
    script_id: int,
    actor: User,
    *,
    name: str | None = None,
    description: str | None = None,
    path: str | None = None,
    is_enabled: bool | None = None,
    ip_address: str | None = None,
) -> Script:
    script = _get_script(session, script_id)

    changes: dict[str, dict] = {}
    if name is not None and name != script.name:
        other = ScriptRepository(session).get_by_name(name)
        if other is not None and other.id != script.id:
            raise ScriptNameConflictError
        changes["name"] = {"from": script.name, "to": name}
        script.name = name

    if description is not None and description != script.description:
        changes["description"] = {"from": script.description, "to": description}
        script.description = description

    if path is not None and path != script.path:
        validated = canonicalize_script_path(path)
        changes["path"] = {"from": script.path, "to": str(validated.path)}
        script.path = str(validated.path)

    if is_enabled is not None and is_enabled != script.is_enabled:
        changes["is_enabled"] = {"from": script.is_enabled, "to": is_enabled}
        script.is_enabled = is_enabled

    if not changes:
        return script

    audit_service.record_event(
        session,
        AuditAction.SCRIPT_UPDATED,
        user_id=actor.id,
        username=actor.username,
        resource="script",
        resource_id=str(script.id),
        ip_address=ip_address,
        details={"name": script.name, "changed_fields": sorted(changes)},
        commit=False,
    )
    if "is_enabled" in changes:
        action = AuditAction.SCRIPT_ENABLED if script.is_enabled else AuditAction.SCRIPT_DISABLED
        audit_service.record_event(
            session,
            action,
            user_id=actor.id,
            username=actor.username,
            resource="script",
            resource_id=str(script.id),
            ip_address=ip_address,
            details={"name": script.name, "is_enabled": script.is_enabled},
            commit=False,
        )
    session.commit()
    return script


def delete_script(
    session: Session,
    script_id: int,
    actor: User,
    *,
    ip_address: str | None = None,
) -> None:
    """Soft-delete a script.

    A script that is still referenced by any (non-deleted) CronJob cannot be
    deleted; execution history is preserved in every case.
    """
    script = _get_script(session, script_id)

    if ScriptRepository(session).is_referenced_by_active_job(script_id):
        raise ScriptInUseError

    script.is_deleted = True
    audit_service.record_event(
        session,
        AuditAction.SCRIPT_DELETED,
        user_id=actor.id,
        username=actor.username,
        resource="script",
        resource_id=str(script.id),
        ip_address=ip_address,
        details={"name": script.name, "path": script.path},
        commit=False,
    )
    session.commit()