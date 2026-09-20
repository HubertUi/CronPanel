"""CronJob management endpoints.

Transport only: permissions via `require_permissions`, business logic and
per-owner access control live in `cron_job_service`.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_permissions
from app.core.permissions import Permission
from app.database.database import get_db
from app.execution.policy import ScriptPathError
from app.models.user import User
from app.schemas.cron_job import (
    CronJobCreate,
    CronJobHistoryResponse,
    CronJobResponse,
    CronJobStatusUpdate,
    CronJobUpdate,
    CronValidateRequest,
    CronValidateResponse,
)
from app.schemas.execution import ExecutionResponse
from app.services import cron_job_service, execution_service
from app.utils import cron_validator
from app.utils.request import get_client_ip

router = APIRouter(prefix="/api/cron-jobs", tags=["cron-jobs"])


def _error(status_code: int, error: str, message: str, **extra) -> HTTPException:
    detail = {"error": error, "message": message, **extra}
    return HTTPException(status_code=status_code, detail=detail)


def _to_response(job) -> CronJobResponse:
    return CronJobResponse(
        id=job.id,
        name=job.name,
        description=job.description,
        command=job.command,
        schedule_expression=job.schedule_expression,
        minute=job.minute,
        hour=job.hour,
        day_of_month=job.day_of_month,
        month=job.month,
        day_of_week=job.day_of_week,
        human_description=cron_validator.describe_cron_expression(job.schedule_expression),
        is_active=job.is_active,
        owner_id=job.owner_id,
        script_id=job.script_id,
        script_name=job.script.name if job.script else None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _parse_changes(raw: str | None) -> dict | None:
    """Parse the history JSON `changes` column defensively (never raises)."""
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


@router.get("", response_model=list[CronJobResponse])
def list_cron_jobs(
    active: bool | None = None,
    owner_id: int | None = None,
    name: str | None = None,
    schedule: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_READ)),
    db: Session = Depends(get_db),
) -> list[CronJobResponse]:
    filters = cron_job_service.CronJobFilter(
        owner_id=owner_id,
        is_active=active,
        name=name,
        schedule=schedule,
        limit=limit,
        offset=offset,
    )
    jobs = cron_job_service.list_cron_jobs(db, current_user, filters)
    return [_to_response(job) for job in jobs]


@router.post("", response_model=CronJobResponse, status_code=status.HTTP_201_CREATED)
def create_cron_job(
    body: CronJobCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_CREATE)),
    db: Session = Depends(get_db),
) -> CronJobResponse:
    try:
        job = cron_job_service.create_cron_job(
            db,
            name=body.name,
            description=body.description,
            command=body.command,
            schedule_expression=body.schedule_expression,
            owner=current_user,
            script_id=body.script_id,
            ip_address=get_client_ip(request),
        )
    except cron_job_service.ScriptReferenceNotFoundError:
        raise _error(400, "SCRIPT_NOT_FOUND", "El script asignado no existe.")
    return _to_response(job)


@router.get("/{cron_job_id}", response_model=CronJobResponse)
def get_cron_job(
    cron_job_id: int,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_READ)),
    db: Session = Depends(get_db),
) -> CronJobResponse:
    try:
        job = cron_job_service.get_cron_job(db, cron_job_id, current_user)
    except cron_job_service.CronJobNotFoundError:
        raise _error(404, "CRON_JOB_NOT_FOUND", "Tarea no encontrada.")
    return _to_response(job)


@router.get("/{cron_job_id}/history", response_model=list[CronJobHistoryResponse])
def get_cron_job_history(
    cron_job_id: int,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_READ)),
    db: Session = Depends(get_db),
) -> list[CronJobHistoryResponse]:
    try:
        entries = cron_job_service.list_cron_job_history(
            db, cron_job_id, current_user, limit=limit, offset=offset
        )
    except cron_job_service.CronJobNotFoundError:
        raise _error(404, "CRON_JOB_NOT_FOUND", "Tarea no encontrada.")
    return [
        CronJobHistoryResponse(
            id=entry.id,
            cron_job_id=entry.cron_job_id,
            username=entry.username,
            action=entry.action,
            changes=_parse_changes(entry.changes),
            timestamp=entry.timestamp,
        )
        for entry in entries
    ]


@router.put("/{cron_job_id}", response_model=CronJobResponse)
def update_cron_job(
    cron_job_id: int,
    body: CronJobUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_UPDATE)),
    db: Session = Depends(get_db),
) -> CronJobResponse:
    try:
        job = cron_job_service.update_cron_job(
            db,
            cron_job_id,
            current_user,
            name=body.name,
            description=body.description,
            command=body.command,
            schedule_expression=body.schedule_expression,
            script_id=body.script_id,
            ip_address=get_client_ip(request),
        )
    except cron_job_service.CronJobNotFoundError:
        raise _error(404, "CRON_JOB_NOT_FOUND", "Tarea no encontrada.")
    except cron_job_service.CronJobAccessDeniedError:
        raise _error(403, "CRON_JOB_FORBIDDEN", "No tiene permisos sobre esta tarea.")
    except cron_job_service.ScriptReferenceNotFoundError:
        raise _error(400, "SCRIPT_NOT_FOUND", "El script asignado no existe.")
    return _to_response(job)


@router.patch("/{cron_job_id}/status", response_model=CronJobResponse)
def update_cron_job_status(
    cron_job_id: int,
    body: CronJobStatusUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_ENABLE)),
    db: Session = Depends(get_db),
) -> CronJobResponse:
    try:
        job = cron_job_service.update_cron_job_status(
            db,
            cron_job_id,
            current_user,
            is_active=body.is_active,
            ip_address=get_client_ip(request),
        )
    except cron_job_service.CronJobNotFoundError:
        raise _error(404, "CRON_JOB_NOT_FOUND", "Tarea no encontrada.")
    except cron_job_service.CronJobAccessDeniedError:
        raise _error(403, "CRON_JOB_FORBIDDEN", "No tiene permisos sobre esta tarea.")
    return _to_response(job)


@router.delete("/{cron_job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cron_job(
    cron_job_id: int,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.CRON_JOBS_DELETE)),
    db: Session = Depends(get_db),
) -> None:
    try:
        cron_job_service.delete_cron_job(
            db,
            cron_job_id,
            current_user,
            ip_address=get_client_ip(request),
        )
    except cron_job_service.CronJobNotFoundError:
        raise _error(404, "CRON_JOB_NOT_FOUND", "Tarea no encontrada.")
    except cron_job_service.CronJobAccessDeniedError:
        raise _error(403, "CRON_JOB_FORBIDDEN", "No tiene permisos sobre esta tarea.")


@router.post("/{cron_job_id}/execute", response_model=ExecutionResponse)
def execute_cron_job(
    cron_job_id: int,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.EXECUTIONS_EXECUTE)),
    db: Session = Depends(get_db),
) -> ExecutionResponse:
    try:
        execution = execution_service.run_cron_job(
            db,
            cron_job_id,
            current_user,
            ip_address=get_client_ip(request),
        )
    except cron_job_service.CronJobNotFoundError:
        raise _error(404, "CRON_JOB_NOT_FOUND", "Tarea no encontrada.")
    except cron_job_service.CronJobAccessDeniedError:
        raise _error(403, "CRON_JOB_FORBIDDEN", "No tiene permisos sobre esta tarea.")
    except execution_service.JobInactiveError:
        raise _error(400, "JOB_INACTIVE", "La tarea está desactivada y no se puede ejecutar.")
    except execution_service.ScriptNotLinkedError:
        raise _error(400, "SCRIPT_REQUIRED", "La tarea no tiene un script asignado.")
    except execution_service.ScriptUnavailableError:
        raise _error(400, "SCRIPT_UNAVAILABLE", "El script asignado no está disponible o está desactivado.")
    except ScriptPathError as exc:
        raise _error(400, exc.code, str(exc))
    return _to_execution_response(execution)


def _to_execution_response(execution) -> ExecutionResponse:
    return ExecutionResponse(
        id=execution.id,
        cron_job_id=execution.cron_job_id,
        cron_job_name=execution.cron_job.name if execution.cron_job else None,
        script_id=execution.script_id,
        script_name=execution.script.name if execution.script else None,
        trigger=execution.trigger,
        status=execution.status,
        exit_code=execution.exit_code,
        stdout=execution.stdout,
        stderr=execution.stderr,
        error=execution.error,
        duration_ms=execution.duration_ms,
        username=execution.username,
        ip_address=execution.ip_address,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )


@router.post("/validate", response_model=CronValidateResponse)
def validate_cron_expression(
    body: CronValidateRequest,
    current_user: User = Depends(get_current_user),
) -> CronValidateResponse:
    result = cron_validator.validate_cron_expression(body.schedule_expression)
    description = None
    if result.valid and result.normalized_expression is not None:
        try:
            description = cron_validator.describe_cron_expression(
                result.normalized_expression
            )
        except cron_validator.CronValidationError:
            description = None
    return CronValidateResponse(
        valid=result.valid,
        normalized_expression=result.normalized_expression,
        fields=result.fields,
        description=description,
        error_code=result.error_code,
        error_message=result.error_message,
        error_field=result.error_field,
    )