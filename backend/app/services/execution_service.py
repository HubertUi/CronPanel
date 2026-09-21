"""Execution business logic: the controlled run pipeline.

Pipeline (Phase 4): User → CronJob → RBAC → ownership → policy (script exists,
is enabled, canonical path inside the allow-list) → executor → persisted result.

Security contract
-----------------
- The executed argv is derived only from a *registered* script id referenced
  by the CronJob. Free-form command strings are never interpreted.
- If any policy check fails the run is rejected *before* a process starts.
- The process runs with a minimal, secret-free environment and a hard timeout.
- Output is captured and capped; everything lands in the `executions` table and
  the audit trail. No shell is ever spawned.
"""

from sqlalchemy.orm import Session

from app.core import audit_actions as AuditAction
from app.core.config import settings
from app.core.execution_status import (
    FAILED,
    RUNNING,
    SUCCESS,
    SYSTEM_ACTOR_USERNAME,
    TIMED_OUT,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
)
from app.core.permissions import is_full_access_role
from app.execution.executor import execute_script
from app.execution.policy import ScriptPathError, canonicalize_script_path
from app.models.cron_job import CronJob
from app.models.execution import Execution
from app.models.user import User
from app.repositories.cron_job_repository import CronJobRepository
from app.repositories.execution_repository import ExecutionRepository, ScriptRepository
from app.services import audit_service
from app.services.cron_job_service import (
    CronJobAccessDeniedError,
    CronJobNotFoundError,
)
from app.utils.datetime import utc_now


class JobInactiveError(Exception):
    pass


class ScriptNotLinkedError(Exception):
    pass


class ScriptUnavailableError(Exception):
    pass


class ExecutionNotFoundError(Exception):
    pass


def _can_execute(job: CronJob, actor: User) -> bool:
    return job.owner_id == actor.id or is_full_access_role(actor.role_name)


def _resolve_script(session: Session, job: CronJob):
    """Fetch and validate the script a job is bound to.

    Raises domain errors *before* any process could start.
    """
    if job.script_id is None:
        raise ScriptNotLinkedError

    script = ScriptRepository(session).get_by_id_include_deleted(job.script_id)
    if script is None or script.is_deleted or not script.is_enabled:
        raise ScriptUnavailableError

    validated = canonicalize_script_path(script.path)
    return script, validated


def run_cron_job(
    session: Session,
    job_id: int,
    actor: User,
    *,
    ip_address: str | None = None,
) -> Execution:
    """Execute a CronJob's bound script synchronously and persist the result.

    Manual invocation (web UI / API): ownership + RBAC are enforced.
    """
    job = CronJobRepository(session).get_by_id(job_id)
    if job is None:
        raise CronJobNotFoundError
    if not _can_execute(job, actor):
        raise CronJobAccessDeniedError
    return _run(
        session,
        job,
        trigger=TRIGGER_MANUAL,
        actor_id=actor.id,
        actor_username=actor.username,
        ip_address=ip_address,
    )


def run_scheduled_cron_job(
    session: Session,
    job_id: int,
) -> Execution:
    """Execute a CronJob on behalf of the internal scheduler.

    There is no user session behind this call: the scheduled run is a system
    operation, so ownership/RBAC do not apply. Every Phase 4 policy check
    (job active, script exists/enabled/inside the allow-list) still runs
    before any process starts. The audit trail records the actor as the
    system, never a real user.
    """
    job = CronJobRepository(session).get_by_id(job_id)
    if job is None:
        raise CronJobNotFoundError
    return _run(
        session,
        job,
        trigger=TRIGGER_SCHEDULED,
        actor_id=None,
        actor_username=SYSTEM_ACTOR_USERNAME,
        ip_address=None,
    )


def _run(
    session: Session,
    job: CronJob,
    *,
    trigger: str,
    actor_id: int | None,
    actor_username: str | None,
    ip_address: str | None,
) -> Execution:
    """Shared execution pipeline: policy → executor → persisted result + audit."""
    if not job.is_active:
        raise JobInactiveError

    script, validated = _resolve_script(session, job)

    execution = Execution(
        cron_job_id=job.id,
        script_id=script.id,
        trigger=trigger,
        status=RUNNING,
        username=actor_username,
        ip_address=ip_address,
    )
    ExecutionRepository(session).add(execution, commit=False)
    audit_service.record_event(
        session,
        AuditAction.EXECUTION_STARTED,
        user_id=actor_id,
        username=actor_username,
        resource="execution",
        resource_id=str(execution.id),
        ip_address=ip_address,
        details={
            "cron_job_id": job.id,
            "cron_job_name": job.name,
            "script_id": script.id,
            "script_name": script.name,
            "trigger": trigger,
        },
        commit=True,
    )

    result = execute_script(
        script_path=validated.path,
        timeout_seconds=settings.EXECUTION_TIMEOUT_SECONDS,
        output_max_chars=settings.EXECUTION_OUTPUT_MAX_CHARS,
    )

    if result.timed_out:
        status = TIMED_OUT
        final_action = AuditAction.EXECUTION_TIMED_OUT
    elif result.exit_code == 0 and result.error is None:
        status = SUCCESS
        final_action = AuditAction.EXECUTION_SUCCEEDED
    else:
        status = FAILED
        final_action = AuditAction.EXECUTION_FAILED

    execution.status = status
    execution.exit_code = result.exit_code
    execution.stdout = result.stdout or None
    execution.stderr = result.stderr or None
    execution.error = result.error
    execution.duration_ms = result.duration_ms
    execution.finished_at = utc_now()

    audit_service.record_event(
        session,
        final_action,
        user_id=actor_id,
        username=actor_username,
        resource="execution",
        resource_id=str(execution.id),
        ip_address=ip_address,
        details={
            "cron_job_id": job.id,
            "cron_job_name": job.name,
            "script_id": script.id,
            "script_name": script.name,
            "status": status,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "trigger": trigger,
        },
        commit=False,
    )
    session.commit()
    return execution


def list_executions(
    session: Session,
    actor: User,
    *,
    job_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Execution]:
    """Executions are scoped by job ownership: regular users see only the
    executions of the jobs they own; full-access roles see everything."""
    repo = ExecutionRepository(session)
    if is_full_access_role(actor.role_name):
        cron_job_ids: list[int] | None = [job_id] if job_id is not None else None
    else:
        owned = repo.list_owned_job_ids(actor.id)
        if job_id is not None:
            if job_id not in owned:
                return []
            cron_job_ids = [job_id]
        else:
            if not owned:
                return []
            cron_job_ids = owned
    return repo.list(
        cron_job_ids=cron_job_ids,
        status=status,
        limit=limit,
        offset=offset,
    )


def get_execution(session: Session, execution_id: int, actor: User) -> Execution:
    """A single execution is visible only to the job's owner / full-access
    roles; otherwise the record is treated as nonexistent (no leak)."""
    execution = ExecutionRepository(session).get_by_id(execution_id)
    if execution is None or execution.cron_job is None:
        raise ExecutionNotFoundError
    if not _can_execute(execution.cron_job, actor):
        raise ExecutionNotFoundError
    return execution