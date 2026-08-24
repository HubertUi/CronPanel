"""Tests for the RBAC permission mapping."""

from app.core.permissions import (
    Permission,
    ROLE_ADMIN,
    ROLE_OPERATOR,
    ROLE_VIEWER,
    get_role_permissions,
    has_permission,
)


def test_admin_has_all_permissions():
    admin_permissions = get_role_permissions(ROLE_ADMIN)
    assert Permission.USERS_DELETE in admin_permissions
    assert Permission.AUDIT_READ in admin_permissions
    assert Permission.SETTINGS_UPDATE in admin_permissions
    assert Permission.TASKS_EXECUTE in admin_permissions


def test_operator_cannot_administer_users_or_settings():
    operator_permissions = get_role_permissions(ROLE_OPERATOR)
    assert Permission.TASKS_CREATE in operator_permissions
    assert Permission.TASKS_EXECUTE in operator_permissions

    assert Permission.USERS_CREATE not in operator_permissions
    assert Permission.USERS_DELETE not in operator_permissions
    assert Permission.AUDIT_READ not in operator_permissions
    assert Permission.SETTINGS_UPDATE not in operator_permissions


def test_viewer_is_read_only():
    viewer_permissions = get_role_permissions(ROLE_VIEWER)
    assert Permission.TASKS_READ in viewer_permissions
    assert Permission.EXECUTIONS_READ in viewer_permissions

    for forbidden in (
        Permission.TASKS_CREATE,
        Permission.TASKS_UPDATE,
        Permission.TASKS_DELETE,
        Permission.TASKS_EXECUTE,
        Permission.USERS_READ,
    ):
        assert forbidden not in viewer_permissions


def test_has_permission_false_for_unknown_role():
    assert has_permission("nonexistent-role", Permission.TASKS_READ) is False
