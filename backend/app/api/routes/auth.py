"""Authentication endpoints: login, logout, current user."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.permissions import get_role_permissions
from app.database.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LogoutResponse, TokenResponse
from app.schemas.user import MeResponse
from app.services import auth_service

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
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenResponse:
    # Generic error for every failure mode to avoid username enumeration.
    user = auth_service.authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise INVALID_CREDENTIALS

    UserRepository(db).update_last_login(user)

    access_token, expires_in = auth_service.issue_access_token(user)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", response_model=LogoutResponse)
def logout(current_user: User = Depends(get_current_user)) -> LogoutResponse:
    # JWT is stateless in this phase: the client discards the token.
    # Server-side revocation/blacklisting is planned for the hardening phase.
    del current_user  # authenticated-only endpoint
    return LogoutResponse(message="Sesión cerrada.")


@router.get("/me", response_model=MeResponse)
def read_current_user(current_user: User = Depends(get_current_user)) -> MeResponse:
    return _to_me_response(current_user)
