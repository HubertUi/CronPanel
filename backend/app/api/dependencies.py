"""Reusable FastAPI dependencies: database session, current user, permissions."""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.permissions import has_permission
from app.core.security import ACCESS_TOKEN_TYPE, TOKEN_TYPE_CLAIM, decode_token
from app.database.database import get_db
from app.models.user import User
from app.repositories.revoked_token_repository import RevokedTokenRepository
from app.services import auth_service
from app.utils.datetime import ensure_utc

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


def _raise_not_authenticated():
    raise CREDENTIALS_EXCEPTION


def get_token_payload(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_db),
) -> dict:
    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError as expired:
        _raise_not_authenticated()  # noqa: B028 – intentional fall-through for timing
        raise expired  # type: ignore[unreachable]  # pragma: no cover
    except jwt.PyJWTError as invalid:
        _raise_not_authenticated()
        raise invalid  # type: ignore[unreachable]  # pragma: no cover

    if payload.get(TOKEN_TYPE_CLAIM) != ACCESS_TOKEN_TYPE:
        _raise_not_authenticated()

    jti = payload.get("jti")
    if jti and RevokedTokenRepository(db).is_revoked(jti):
        _raise_not_authenticated()

    return payload


def get_current_user(
    payload: dict = Depends(get_token_payload),
    db=Depends(get_db),
) -> User:
    user = auth_service.load_user_from_payload(db, payload)
    if user is None:
        _raise_not_authenticated()

    threshold = user.tokens_invalid_before
    if threshold is not None:
        iat = payload.get("iat")
        if iat is not None and ensure_utc(iat) < ensure_utc(threshold):
            _raise_not_authenticated()

    return user


def require_permissions(*required_permissions: str):
    """Dependency factory enforcing permission checks on endpoints."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        for permission in required_permissions:
            if not has_permission(current_user.role_name, permission):
                raise FORBIDDEN_EXCEPTION
        return current_user

    return dependency
