"""Script (allow-list) management endpoints.

Transport only. RBAC gates the entry points: reading requires ``scripts.read``
(every role), registration/update/delete require the admin-only ``scripts.*``
write permissions. The execution policy validates paths at registration.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_permissions
from app.core.permissions import Permission
from app.database.database import get_db
from app.execution.policy import ScriptPathError
from app.models.user import User
from app.schemas.script import ScriptCreate, ScriptResponse, ScriptUpdate
from app.services import script_service
from app.utils.request import get_client_ip

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


def _error(status_code: int, error: str, message: str, **extra) -> HTTPException:
    detail = {"error": error, "message": message, **extra}
    return HTTPException(status_code=status_code, detail=detail)


def _to_response(script) -> ScriptResponse:
    return ScriptResponse(
        id=script.id,
        name=script.name,
        description=script.description,
        path=script.path,
        is_enabled=script.is_enabled,
        created_by=script.created_by,
        created_by_username=script.creator.username if script.creator else None,
        created_at=script.created_at,
        updated_at=script.updated_at,
    )


@router.get("", response_model=list[ScriptResponse])
def list_scripts(
    current_user: User = Depends(require_permissions(Permission.SCRIPTS_READ)),
    db: Session = Depends(get_db),
) -> list[ScriptResponse]:
    return [_to_response(script) for script in script_service.list_scripts(db)]


@router.post("", response_model=ScriptResponse, status_code=status.HTTP_201_CREATED)
def create_script(
    body: ScriptCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.SCRIPTS_CREATE)),
    db: Session = Depends(get_db),
) -> ScriptResponse:
    try:
        script = script_service.create_script(
            db,
            current_user,
            name=body.name,
            description=body.description,
            path=body.path,
            ip_address=get_client_ip(request),
        )
    except ScriptPathError as exc:
        raise _error(400, exc.code, str(exc))
    except script_service.ScriptNameConflictError:
        raise _error(409, "SCRIPT_NAME_CONFLICT", "Ya existe un script con ese nombre.")
    return _to_response(script)


@router.get("/{script_id}", response_model=ScriptResponse)
def get_script(
    script_id: int,
    current_user: User = Depends(require_permissions(Permission.SCRIPTS_READ)),
    db: Session = Depends(get_db),
) -> ScriptResponse:
    try:
        script = script_service.get_script(db, script_id)
    except script_service.ScriptNotFoundError:
        raise _error(404, "SCRIPT_NOT_FOUND", "Script no encontrado.")
    return _to_response(script)


@router.put("/{script_id}", response_model=ScriptResponse)
def update_script(
    script_id: int,
    body: ScriptUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.SCRIPTS_UPDATE)),
    db: Session = Depends(get_db),
) -> ScriptResponse:
    try:
        script = script_service.update_script(
            db,
            script_id,
            current_user,
            name=body.name,
            description=body.description,
            path=body.path,
            is_enabled=body.is_enabled,
            ip_address=get_client_ip(request),
        )
    except script_service.ScriptNotFoundError:
        raise _error(404, "SCRIPT_NOT_FOUND", "Script no encontrado.")
    except ScriptPathError as exc:
        raise _error(400, exc.code, str(exc))
    except script_service.ScriptNameConflictError:
        raise _error(409, "SCRIPT_NAME_CONFLICT", "Ya existe un script con ese nombre.")
    return _to_response(script)


@router.delete("/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(
    script_id: int,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.SCRIPTS_DELETE)),
    db: Session = Depends(get_db),
) -> None:
    try:
        script_service.delete_script(
            db,
            script_id,
            current_user,
            ip_address=get_client_ip(request),
        )
    except script_service.ScriptNotFoundError:
        raise _error(404, "SCRIPT_NOT_FOUND", "Script no encontrado.")
    except script_service.ScriptInUseError:
        raise _error(409, "SCRIPT_IN_USE", "El script está en uso por una tarea y no se puede eliminar.")