"""User administration business logic.

Contains the admin-only rules for creating, updating and deleting users.
Guards against accidental self-deletion and removal of the last active admin.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core import audit_actions as AuditAction
from app.core.password_policy import WeakPasswordError, enforce_password_policy
from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services import audit_service


class UserNotFoundError(Exception):
    pass


class DuplicateIdentityError(Exception):
    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"El valor de '{field}' ya está en uso.")


class LastAdminProtectedError(Exception):
    pass


class SelfDeleteError(Exception):
    pass


class CannotModifySelfRoleError(Exception):
    pass


def get_user_or_none(session: Session, user_id: int) -> User | None:
    return UserRepository(session).get_by_id(user_id)


def get_user_or_raise(session: Session, user_id: int) -> User:
    user = get_user_or_none(session, user_id)
    if user is None:
        raise UserNotFoundError
    return user


def _ensure_not_last_active_admin(session: Session, target_user: User) -> None:
    if target_user.role_name != "admin" or not target_user.is_active:
        return
    repository = UserRepository(session)
    count = repository.count_active_admins()
    if count <= 1:
        raise LastAdminProtectedError


def create_user(
    session: Session,
    username: str,
    email: str,
    password: str,
    role: str,
    actor: User,
    *,
    ip_address: str | None = None,
) -> User:
    repository = UserRepository(session)

    if repository.get_by_username(username) is not None:
        raise DuplicateIdentityError("username")
    if repository.get_by_email(email) is not None:
        raise DuplicateIdentityError("email")

    enforce_password_policy(password, username=username)
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
        role_id=_get_role_id(session, role),
    )
    session.add(user)
    session.flush()

    audit_service.record_event(
        session,
        AuditAction.USER_CREATE,
        user_id=user.id,
        username=actor.username,
        resource="user",
        resource_id=str(user.id),
        ip_address=ip_address,
        details={"created_username": username, "role": role},
        commit=True,
    )
    return user


def update_user(
    session: Session,
    target_id: int,
    *,
    email: str | None = None,
    password: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    actor: User,
    ip_address: str | None = None,
) -> User:
    repository = UserRepository(session)
    user = get_user_or_raise(session, target_id)
    actor_is_target = actor.id == target_id

    if is_active is not None and is_active != user.is_active:
        if user.role_name == "admin":
            _ensure_not_last_active_admin(session, user)
        user.is_active = is_active
        audit_action = AuditAction.USER_ACTIVATE if is_active else AuditAction.USER_DEACTIVATE
        audit_service.record_event(
            session,
            audit_action,
            user_id=target_id,
            username=actor.username,
            resource="user",
            resource_id=str(target_id),
            ip_address=ip_address,
            commit=False,
        )
        if not is_active:
            from app.services.auth_service import _revoke_all_tokens_for_user

            _revoke_all_tokens_for_user(session, user, commit=False)

    if role is not None and role != user.role_name:
        if actor_is_target:
            raise CannotModifySelfRoleError("No puede cambiar su propio rol.")
        if user.role_name == "admin":
            _ensure_not_last_active_admin(session, user)
        old_role = user.role_name
        from app.models.role import Role

        role_obj = session.query(Role).filter(Role.name == role).one_or_none()
        if role_obj is None:
            raise ValueError(f"Rol '{role}' no existe.")
        user.role_id = role_obj.id
        from app.services.auth_service import _revoke_all_tokens_for_user

        _revoke_all_tokens_for_user(session, user, commit=False)
        audit_service.record_event(
            session,
            AuditAction.ROLE_CHANGE,
            user_id=target_id,
            username=actor.username,
            resource="user",
            resource_id=str(target_id),
            ip_address=ip_address,
            details={"old_role": old_role, "new_role": role},
            commit=False,
        )

    if email is not None and email != user.email:
        existing = repository.get_by_email(email)
        if existing is not None and existing.id != target_id:
            raise DuplicateIdentityError("email")
        user.email = email
        audit_service.record_event(
            session,
            AuditAction.USER_UPDATE,
            user_id=target_id,
            username=actor.username,
            resource="user",
            resource_id=str(target_id),
            ip_address=ip_address,
            details={"changed_field": "email"},
            commit=False,
        )

    if password is not None:
        enforce_password_policy(password, username=user.username)
        user.hashed_password = hash_password(password)
        from app.services.auth_service import _revoke_all_tokens_for_user

        _revoke_all_tokens_for_user(session, user, commit=False)
        audit_service.record_event(
            session,
            AuditAction.PASSWORD_RESET,
            user_id=target_id,
            username=actor.username,
            resource="user",
            resource_id=str(target_id),
            ip_address=ip_address,
            commit=False,
        )

    session.commit()
    return user


def delete_user(
    session: Session,
    target_id: int,
    *,
    actor: User,
    ip_address: str | None = None,
) -> None:
    user = get_user_or_raise(session, target_id)

    if user.role_name == "admin":
        _ensure_not_last_active_admin(session, user)

    if actor.id == target_id:
        raise SelfDeleteError("No puede eliminar su propia cuenta.")

    deleted_username = user.username
    session.delete(user)
    audit_service.record_event(
        session,
        AuditAction.USER_DELETE,
        user_id=target_id,
        username=actor.username,
        resource="user",
        resource_id=str(target_id),
        ip_address=ip_address,
        details={"deleted_username": deleted_username},
        commit=True,
    )


def list_users(session: Session) -> list[User]:
    return UserRepository(session).list_users()


def _get_role_id(session: Session, role_name: str) -> int:
    from app.models.role import Role

    role = session.query(Role).filter(Role.name == role_name).one_or_none()
    if role is None:
        raise ValueError(f"Rol '{role_name}' no existe.")
    return role.id
