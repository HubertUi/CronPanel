"""Reusable permission system (RBAC).

Permissions follow the `resource.action` convention. Roles map to a set of
permissions; authorization checks should always be done against permissions,
never against role names directly (`user.role == "admin"` is forbidden).

Adding a new role only requires adding an entry to ROLE_PERMISSIONS.
"""

from dataclasses import dataclass


class Permission:
    # Users
    USERS_READ = "users.read"
    USERS_CREATE = "users.create"
    USERS_UPDATE = "users.update"
    USERS_DELETE = "users.delete"

    # Tasks
    TASKS_READ = "tasks.read"
    TASKS_CREATE = "tasks.create"
    TASKS_UPDATE = "tasks.update"
    TASKS_DELETE = "tasks.delete"
    TASKS_EXECUTE = "tasks.execute"

    # Scripts
    SCRIPTS_READ = "scripts.read"
    SCRIPTS_CREATE = "scripts.create"
    SCRIPTS_UPDATE = "scripts.update"
    SCRIPTS_DELETE = "scripts.delete"
    SCRIPTS_EXECUTE = "scripts.execute"

    # Executions
    EXECUTIONS_READ = "executions.read"

    # Audit
    AUDIT_READ = "audit.read"

    # Settings
    SETTINGS_READ = "settings.read"
    SETTINGS_UPDATE = "settings.update"


ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    permission
    for attribute, permission in vars(Permission).items()
    if not attribute.startswith("_") and isinstance(permission, str)
)

_ADMIN_PERMISSIONS = ALL_PERMISSIONS

_OPERATOR_PERMISSIONS = frozenset(
    {
        Permission.TASKS_READ,
        Permission.TASKS_CREATE,
        Permission.TASKS_UPDATE,
        Permission.TASKS_DELETE,
        Permission.TASKS_EXECUTE,
        Permission.SCRIPTS_READ,
        Permission.EXECUTIONS_READ,
    }
)

_VIEWER_PERMISSIONS = frozenset(
    {
        Permission.TASKS_READ,
        Permission.EXECUTIONS_READ,
    }
)

ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_ADMIN: "Full system administration.",
    ROLE_OPERATOR: "Can manage and execute tasks, read scripts and executions.",
    ROLE_VIEWER: "Read-only access to tasks and executions.",
}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_ADMIN: _ADMIN_PERMISSIONS,
    ROLE_OPERATOR: _OPERATOR_PERMISSIONS,
    ROLE_VIEWER: _VIEWER_PERMISSIONS,
}


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    description: str


SYSTEM_ROLES: tuple[RoleDefinition, ...] = tuple(
    RoleDefinition(name=name, description=ROLE_DESCRIPTIONS[name]) for name in sorted(ROLE_PERMISSIONS)
)


def get_role_permissions(role_name: str) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(role_name, frozenset())


def has_permission(role_name: str, permission: str) -> bool:
    return permission in get_role_permissions(role_name)
