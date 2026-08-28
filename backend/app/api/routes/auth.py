"""Authentication endpoints: login, logout, change password, current user."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, oauth2_scheme
from app.core import audit_actions as AuditAction
from app.core.password_policy import WeakPasswordError
from app.core.permissions import get_role_permissions
from app.core.rate_limit import login_rate_key, login_rate_limiter
from app.core.security import decode_token
from app.database.database import get_db
from app.models.user import User
from app.repositories.revoked_token_repository import RevokedTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import ChangePasswordRequest, LogoutResponse, TokenResponse
from app.schemas.user import MeResponse
from app.services import auth_service, audit_service
from app.utils.request import get_client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"error": "INVALID_CREDENTIALS", "message": "Usuario o contraseña incorrectos."},
    headers={"WWW-Authenticate": "Bearer"},
)


def _to_me_response(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role_name,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        permissions=sorted(get_role_permissions(user.role_name)),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip = get_client_ip(request)
    key = login_rate_key(ip, form_data.username)

    if login_rate_limiter.is_blocked(key):
        remaining = login_rate_limiter.seconds_until_unblocked(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "RATE_LIMITED",
                "message": "Demasiados intentos. Espere antes de reintentar.",
            },
            headers={"Retry-After": str(remaining)},
        )

    user = auth_service.authenticate_user(db, form_data.username, form_data.password, ip_address=ip)
    if user is None:
        login_rate_limiter.register_failure(key)
        raise INVALID_CREDENTIALS

    login_rate_limiter.reset_key(key)
    UserRepository(db).update_last_login(user)

    access_token, expires_in = auth_service.issue_access_token(user)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
) -> LogoutResponse:
    payload = decode_token(token)
    jti = payload.get("jti")
    expires_at = payload.get("exp")
    if jti and expires_at:
        from datetime import datetime, timezone

        expires_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
        RevokedTokenRepository(db).add(
            jti=jti, user_id=current_user.id, expires_at=expires_dt, commit=False
        )

    audit_service.record_event(
        db,
        AuditAction.LOGOUT,
        user_id=current_user.id,
        username=current_user.username,
        ip_address=get_client_ip(request) if request else None,
        resource="session",
        resource_id=payload.get("jti"),
        commit=True,
    )

    # Opportunistic purge of expired revocation entries (keeps table small).
    try:
        RevokedTokenRepository(db).purge_expired()
    except Exception:  # noqa: BLE001
        pass

    return LogoutResponse(message="Sesión cerrada.")


@router.get("/me", response_model=MeResponse)
def read_current_user(current_user: User = Depends(get_current_user)) -> MeResponse:
    return _to_me_response(current_user)


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
) -> dict:
    ip = get_client_ip(request) if request else None
    try:
        auth_service.change_password(
            db,
            current_user,
            body.current_password,
            body.new_password,
            ip_address=ip,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_CURRENT_PASSWORD", "message": str(exc)},
        )
    except WeakPasswordError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "WEAK_PASSWORD",
                "message": "La nueva contraseña no cumple la política de seguridad.",
                "details": exc.violations,
            },
        )
    return {"message": "Contraseña actualizada. Vuelva a iniciar sesión."}
