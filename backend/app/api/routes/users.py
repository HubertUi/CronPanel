"""User administration endpoints. All require users.* permissions (ADMIN)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_permissions
from app.core.permissions import Permission
from app.database.database import get_db
from app.models.user import User
from app.schemas.user import MeResponse, UserCreate, UserResponse, UserUpdate
from app.services import user_service
from app.utils.request import get_client_ip

router = APIRouter(prefix="/api/users", tags=["users"])


def _error(status: int, error: str, message: str, **extra) -> HTTPException:
    detail = {"error": error, "message": message, **extra}
    return HTTPException(status_code=status, detail=detail)


@router.get("", response_model=list[UserResponse])
def list_users(
    current_user: User = Depends(require_permissions(Permission.USERS_READ)),
    db: Session = Depends(get_db),
) -> list[UserResponse]:
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            role=u.role_name,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in user_service.list_users(db)
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.USERS_CREATE)),
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        user = user_service.create_user(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
            role=body.role,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except user_service.DuplicateIdentityError as exc:
        raise _error(409, "DUPLICATE_IDENTITY", str(exc))
    except Exception as exc:
        if "rol" in str(exc).lower() or "role" in str(exc).lower():
            raise _error(422, "INVALID_ROLE", str(exc))
        raise
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    current_user: User = Depends(require_permissions(Permission.USERS_READ)),
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        user = user_service.get_user_or_raise(db, user_id)
    except user_service.UserNotFoundError:
        raise _error(404, "USER_NOT_FOUND", "Usuario no encontrado.")
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.USERS_UPDATE)),
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        user = user_service.update_user(
            db,
            user_id,
            email=body.email,
            password=body.password,
            role=body.role,
            is_active=body.is_active,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except user_service.UserNotFoundError:
        raise _error(404, "USER_NOT_FOUND", "Usuario no encontrado.")
    except user_service.DuplicateIdentityError as exc:
        raise _error(409, "DUPLICATE_IDENTITY", str(exc))
    except user_service.LastAdminProtectedError:
        raise _error(409, "LAST_ADMIN_PROTECTED", "No se puede modificar el último administrador activo.")
    except user_service.CannotModifySelfRoleError as exc:
        raise _error(409, "SELF_ROLE_CHANGE", str(exc))
    except Exception as exc:
        if "contraseña" in str(exc).lower():
            raise
        raise _error(422, "VALIDATION_ERROR", str(exc))
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_permissions(Permission.USERS_DELETE)),
    db: Session = Depends(get_db),
) -> None:
    try:
        user_service.delete_user(
            db,
            user_id,
            actor=current_user,
            ip_address=get_client_ip(request),
        )
    except user_service.UserNotFoundError:
        raise _error(404, "USER_NOT_FOUND", "Usuario no encontrado.")
    except user_service.LastAdminProtectedError:
        raise _error(409, "LAST_ADMIN_PROTECTED", "No se puede eliminar el último administrador activo.")
    except user_service.SelfDeleteError as exc:
        raise _error(409, "SELF_DELETE_FORBIDDEN", str(exc))
