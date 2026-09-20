"""Execution history endpoints (Phase 4).

History is read-only here; starting a run lives on the cron-job resource
(``POST /api/cron-jobs/{id}/execute``) because an execution belongs to a job.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_permissions
from app.core.permissions import Permission
from app.database.database import get_db
from app.models.user import User
from app.schemas.execution import ExecutionResponse
from app.services import execution_service

router = APIRouter(prefix="/api/executions", tags=["executions"])


def _error(status_code: int, error: str, message: str, **extra) -> HTTPException:
    detail = {"error": error, "message": message, **extra}
    return HTTPException(status_code=status_code, detail=detail)


def _to_response(execution) -> ExecutionResponse:
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


@router.get("", response_model=list[ExecutionResponse])
def list_executions(
    job_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(require_permissions(Permission.EXECUTIONS_READ)),
    db: Session = Depends(get_db),
) -> list[ExecutionResponse]:
    executions = execution_service.list_executions(
        db,
        current_user,
        job_id=job_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [_to_response(execution) for execution in executions]


@router.get("/{execution_id}", response_model=ExecutionResponse)
def get_execution(
    execution_id: int,
    current_user: User = Depends(require_permissions(Permission.EXECUTIONS_READ)),
    db: Session = Depends(get_db),
) -> ExecutionResponse:
    try:
        execution = execution_service.get_execution(db, execution_id, current_user)
    except execution_service.ExecutionNotFoundError:
        raise _error(404, "EXECUTION_NOT_FOUND", "Ejecución no encontrada.")
    return _to_response(execution)