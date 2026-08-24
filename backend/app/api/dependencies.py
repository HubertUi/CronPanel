"""Reusable FastAPI dependencies: database session, current user, permissions."""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.permissions import has_permission
from app.core.security import ACCESS_TOKEN_TYPE, TOKEN_TYPE_CLAIM, decode_token
from app.database.database import get_db
from app.models.user import User
from app.services import auth_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"error": "NOT_AUTHENTICATED", "message": "No autenticado o token inválido."},
    headers={"WWW-Authenticate": "Bearer"},
)

FORBIDDEN_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail={
        "error": "PERMISSION_DENIED",
        "message": "No tiene permisos para realizar esta acción.",
    },
)


def _unauthenticated() -> HTTPException:
    return CREDENTIALS_EXCEPTION


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as expired:
        raise _unauthenticated() from expired
    except jwt.PyJWTError as invalid:
        raise _unauthenticated() from invalid

    if payload.get(TOKEN_TYPE_CLAIM) != ACCESS_TOKEN_TYPE:
        raise _unauthenticated()

    user = auth_service.load_user_from_payload(db, payload)
    if user is None:
        raise _unauthenticated()
    return user


def require_permissions(*required_permissions: str):
    """Dependency factory enforcing permission checks on endpoints."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        for permission in required_permissions:
            if not has_permission(current_user.role_name, permission):
                raise FORBIDDEN_EXCEPTION
        return current_user

    return dependency
