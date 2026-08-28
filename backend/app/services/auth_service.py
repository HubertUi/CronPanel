"""Authentication business logic. Routes must not contain auth rules."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core import audit_actions as AuditAction
from app.core.logging import get_logger
from app.core.password_policy import WeakPasswordError, enforce_password_policy
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.revoked_token_repository import RevokedTokenRepository
from app.repositories.user_repository import UserRepository
from app.services import audit_service
from app.utils.datetime import utc_now

logger = get_logger("app.auth")

# Constant-time equalizer: performed when the user does not exist so that
# response timing does not reveal which usernames are registered.
_DUMMY_HASH = hash_password("timing-equalizer-dummy-value")


def _revoke_all_tokens_for_user(
    session: Session, user: User, *, commit: bool = False
) -> None:
    """Invalidate every outstanding token the user might hold.

    Uses the per-user `tokens_invalid_before` threshold (checks `iat` in
    get_current_user) rather than trying to enumerate `jti`s we never recorded.
    """
    user.tokens_invalid_before = utc_now()
    session.flush()
    audit_service.record_event(
        session,
        AuditAction.TOKEN_REVOKED,
        user_id=user.id,
        username=user.username,
        resource="session",
        details={"scope": "all_sessions"},
        commit=commit,
    )


def authenticate_user(
    session: Session,
    username: str,
    password: str,
    ip_address: str | None = None,
) -> User | None:
    """Validate credentials. Returns the user or None (reason logged only)."""
    repository = UserRepository(session)
    user = repository.get_by_username(username)

    if user is None:
        verify_password(password, _DUMMY_HASH)
        audit_service.record_event(
            session,
            AuditAction.LOGIN_FAILED,
            username=username,
            ip_address=ip_address,
            details={"reason": "unknown_user"},
            commit=True,
        )
        logger.info("Login failed: unknown username '%s'.", username)
        return None

    if not verify_password(password, user.hashed_password):
        audit_service.record_event(
            session,
            AuditAction.LOGIN_FAILED,
            user_id=user.id,
            username=user.username,
            ip_address=ip_address,
            details={"reason": "invalid_password"},
            commit=True,
        )
        logger.info("Login failed: invalid password for '%s'.", username)
        return None

    if not user.is_active:
        audit_service.record_event(
            session,
            AuditAction.LOGIN_FAILED,
            user_id=user.id,
            username=user.username,
            ip_address=ip_address,
            details={"reason": "inactive_user"},
            commit=True,
        )
        logger.info("Login failed: inactive user '%s'.", username)
        return None

    audit_service.record_event(
        session,
        AuditAction.LOGIN_SUCCESS,
        user_id=user.id,
        username=user.username,
        ip_address=ip_address,
        commit=True,
    )
    return user


def issue_access_token(user: User) -> tuple[str, int]:
    token, expires_in = create_access_token(
        subject=str(user.id),
        extra_claims={
            "username": user.username,
            "role": user.role_name,
        },
    )
    return token, expires_in


def change_password(
    session: Session,
    user: User,
    current_password: str,
    new_password: str,
    ip_address: str | None = None,
) -> None:
    """Validate current password, enforce policy, hash and save the new one.

    Raises:
        ValueError: if the current password is incorrect.
        WeakPasswordError: if the new password violates the policy.
    """
    if not verify_password(current_password, user.hashed_password):
        audit_service.record_event(
            session,
            AuditAction.PASSWORD_CHANGE_FAILED,
            user_id=user.id,
            username=user.username,
            ip_address=ip_address,
            details={"reason": "wrong_current_password"},
            commit=True,
        )
        raise ValueError("La contraseña actual no es correcta.")

    enforce_password_policy(new_password, username=user.username)
    user.hashed_password = hash_password(new_password)
    _revoke_all_tokens_for_user(session, user, commit=True)

    audit_service.record_event(
        session,
        AuditAction.PASSWORD_CHANGE,
        user_id=user.id,
        username=user.username,
        ip_address=ip_address,
        commit=True,
    )


def load_user_from_payload(session: Session, payload: dict) -> User | None:
    """Resolve a validated JWT payload back to an active User."""
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None

    user = UserRepository(session).get_by_id(user_id)
    if user is None or not user.is_active:
        return None
    return user
