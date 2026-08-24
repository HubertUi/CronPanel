"""Authentication business logic. Routes must not contain auth rules."""

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = get_logger("app.auth")

# Constant-time equalizer: performed when the user does not exist so that
# response timing does not reveal which usernames are registered.
_DUMMY_HASH = hash_password("timing-equalizer-dummy-value")


def authenticate_user(session: Session, username: str, password: str) -> User | None:
    """Validate credentials. Returns the user or None (reason logged only)."""
    repository = UserRepository(session)
    user = repository.get_by_username(username)

    if user is None:
        verify_password(password, _DUMMY_HASH)
        logger.info("Login failed: unknown username '%s'.", username)
        return None

    if not verify_password(password, user.hashed_password):
        logger.info("Login failed: invalid password for '%s'.", username)
        return None

    if not user.is_active:
        logger.info("Login failed: inactive user '%s'.", username)
        return None

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
