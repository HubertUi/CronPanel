"""CronJob business logic: creation, querying, update, status, deletion.

Layered access control:
- The RBAC dependency (`require_permissions`) authorizes *actions*.
- Ownership is enforced here: a job can be viewed/edited by its owner or by
  a full-access role (the administrator); other users cannot touch it.

Important (Phase 3): operations only persist data. No command is ever
executed, no shell is spawned and the system crontab is never touched.
"""

import json

from sqlalchemy.orm import Session

from app.core import audit_actions as AuditAction
from app.core import cron_history_actions as HistoryAction
from app.core.permissions import is_full_access_role
from app.models.cron_job import CronJob
from app.models.cron_job_history import CronJobHistory
from app.models.user import User
from app.repositories.cron_job_repository import CronJobHistoryRepository, CronJobRepository
from app.repositories.execution_repository import ScriptRepository
from app.services import audit_service
from app.utils.cron_validator import parse_cron_expression


class CronJobNotFoundError(Exception):
    pass


class CronJobAccessDeniedError(Exception):
    pass


class ScriptReferenceNotFoundError(Exception):
    pass


class CronJobFilter:
    def __init__(
        self,
        *,
        owner_id: int | None = None,
        is_active: bool | None = None,
        name: str | None = None,
        schedule: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> None:
        self.owner_id = owner_id
        self.is_active = is_active
        self.name = name
        self.schedule = schedule
        self.limit = limit
        self.offset = offset


def _serialize_changes(changes: dict) -> str | None:
    if not changes:
        return None
    return json.dumps(changes, ensure_ascii=False, default=str)


def _apply_schedule(job: CronJob, expression: str) -> None:
    """Sync the derived five fields from the canonical expression."""
    minute, hour, day_of_month, month, day_of_week = parse_cron_expression(expression)
    job.schedule_expression = " ".join([minute, hour, day_of_month, month, day_of_week])
    job.minute = minute
    job.hour = hour
    job.day_of_month = day_of_month
    job.month = month
    job.day_of_week = day_of_week


def _record_history(
    session: Session,
    job: CronJob,
    actor: User,
    action: str,
    changes: dict | None = None,
    *,
    commit: bool = False,
) -> None:
    entry = CronJobHistory(
        cron_job_id=job.id,
        user_id=actor.id,
        username=actor.username,
        action=action,
        changes=_serialize_changes(changes),
    )
    CronJobHistoryRepository(session).add(entry, commit=commit)


def _can_manage(job: CronJob, actor: User) -> bool:
    return job.owner_id == actor.id or is_full_access_role(actor.role_name)


def _get_job_for_read(session: Session, job_id: int) -> CronJob:
    job = CronJobRepository(session).get_by_id(job_id)
    if job is None:
        raise CronJobNotFoundError
    return job


def _get_job_for_write(session: Session, job_id: int, actor: User) -> CronJob:
    job = _get_job_for_read(session, job_id)
    if not _can_manage(job, actor):
        raise CronJobAccessDeniedError
    return job


def _validate_script_reference(session: Session, script_id: int | None) -> None:
    """A job may point only to an existing, non-deleted script."""
    if script_id is None:
        return
    script = ScriptRepository(session).get_by_id(script_id)
    if script is None:
        raise ScriptReferenceNotFoundError


def create_cron_job(
    session: Session,
    *,
    name: str,
    description: str | None,
    command: str,
    schedule_expression: str,
    owner: User,
    script_id: int | None = None,
    ip_address: str | None = None,
) -> CronJob:
    _validate_script_reference(session, script_id)
    job = CronJob(
        name=name,
        description=description,
        command=command,
        is_active=True,
        owner_id=owner.id,
        script_id=script_id,
    )
    _apply_schedule(job, schedule_expression)
    CronJobRepository(session).add(job, commit=False)

    _record_history(session, job, owner, HistoryAction.CREATED, commit=False)
    audit_service.record_event(
        session,
        AuditAction.CRON_JOB_CREATED,
        user_id=owner.id,
        username=owner.username,
        resource="cron_job",
        resource_id=str(job.id),
        ip_address=ip_address,
        details={"name": job.name, "schedule_expression": job.schedule_expression},
        commit=True,
    )
    return job


def get_cron_job(session: Session, job_id: int, actor: User) -> CronJob:
    """Read access: owners and full-access roles; otherwise raise not found
    so the mere existence of a job is never leaked to unauthorized users."""
    job = _get_job_for_read(session, job_id)
    if not _can_manage(job, actor):
        raise CronJobNotFoundError
    return job


def list_cron_jobs(
    session: Session,
    actor: User,
    filters: CronJobFilter,
) -> list[CronJob]:
    """Ownership-scoped listing: regular users only see their own jobs."""
    owner_id = filters.owner_id
    if not is_full_access_role(actor.role_name):
        owner_id = actor.id
    return CronJobRepository(session).list_jobs(
        owner_id=owner_id,
        is_active=filters.is_active,
        name=filters.name,
        schedule=filters.schedule,
        limit=filters.limit,
        offset=filters.offset,
    )


def update_cron_job(
    session: Session,
    job_id: int,
    actor: User,
    *,
    name: str | None = None,
    description: str | None = None,
    command: str | None = None,
    schedule_expression: str | None = None,
    script_id: int | None = None,
    ip_address: str | None = None,
) -> CronJob:
    job = _get_job_for_write(session, job_id, actor)
    if script_id is not None:
        _validate_script_reference(session, script_id)

    changes: dict[str, dict] = {}
    candidates = [
        ("name", name, job.name),
        ("description", description, job.description),
        ("command", command, job.command),
    ]
    for field, new_value, old_value in candidates:
        if new_value is not None and new_value != old_value:
            changes[field] = {"from": old_value, "to": new_value}
            setattr(job, field, new_value)

    if script_id is not None and script_id != job.script_id:
        changes["script_id"] = {"from": job.script_id, "to": script_id}
        job.script_id = script_id

    if schedule_expression is not None and schedule_expression != job.schedule_expression:
        old_expression = job.schedule_expression
        _apply_schedule(job, schedule_expression)
        changes["schedule_expression"] = {"from": old_expression, "to": job.schedule_expression}

    if not changes:
        return job

    _record_history(session, job, actor, HistoryAction.UPDATED, changes=changes, commit=False)
    audit_service.record_event(
        session,
        AuditAction.CRON_JOB_UPDATED,
        user_id=actor.id,
        username=actor.username,
        resource="cron_job",
        resource_id=str(job.id),
        ip_address=ip_address,
        details={"name": job.name, "changed_fields": sorted(changes)},
        commit=False,
    )
    session.commit()
    return job


def update_cron_job_status(
    session: Session,
    job_id: int,
    actor: User,
    *,
    is_active: bool,
    ip_address: str | None = None,
) -> CronJob:
    job = _get_job_for_write(session, job_id, actor)

    if job.is_active == is_active:
        return job

    job.is_active = is_active
    action = HistoryAction.ENABLED if is_active else HistoryAction.DISABLED
    audit_action = AuditAction.CRON_JOB_ENABLED if is_active else AuditAction.CRON_JOB_DISABLED

    _record_history(session, job, actor, action, commit=False)
    audit_service.record_event(
        session,
        audit_action,
        user_id=actor.id,
        username=actor.username,
        resource="cron_job",
        resource_id=str(job.id),
        ip_address=ip_address,
        details={"name": job.name, "is_active": is_active},
        commit=False,
    )
    session.commit()
    return job


def delete_cron_job(
    session: Session,
    job_id: int,
    actor: User,
    *,
    ip_address: str | None = None,
) -> None:
    """Soft-delete: the row and its history are preserved for the audit trail."""
    job = _get_job_for_write(session, job_id, actor)

    job.is_deleted = True
    job.is_active = False
    _record_history(session, job, actor, HistoryAction.DELETED, commit=False)
    audit_service.record_event(
        session,
        AuditAction.CRON_JOB_DELETED,
        user_id=actor.id,
        username=actor.username,
        resource="cron_job",
        resource_id=str(job.id),
        ip_address=ip_address,
        details={"name": job.name, "schedule_expression": job.schedule_expression},
        commit=False,
    )
    session.commit()


def list_cron_job_history(
    session: Session,
    job_id: int,
    actor: User,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[CronJobHistory]:
    """History is only readable by those who can see the job itself.

    Soft-deleted jobs keep their history accessible (read-only) for the
    owner and full-access roles so the audit trail is never lost.
    """
    job = CronJobRepository(session).get_by_id_include_deleted(job_id)
    if job is None:
        raise CronJobNotFoundError
    if not _can_manage(job, actor):
        raise CronJobNotFoundError
    return CronJobHistoryRepository(session).list_for_job(job_id, limit=limit, offset=offset)