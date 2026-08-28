"""Audit service: persists security-relevant events.

The database is the source of truth for the audit trail. Sensitive keys are
stripped from `details` as defense in depth; callers must still avoid
passing credentials explicitly.
"""

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core import audit_actions as AuditAction  # noqa: N812 - re-export namespace
from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditRepository

logger = get_logger("audit")

_SENSITIVE_KEY_MARKERS = ("password", "token", "secret", "credential", "hash")


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(marker in str(key).lower() for marker in _SENSITIVE_KEY_MARKERS)
            else _sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def sanitize_details(details: dict | None) -> str | None:
    if not details:
        return None
    try:
        return json.dumps(_sanitize_value(details), ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"serialization_error": True})


def record_event(
    session: Session,
    action: str,
    *,
    user_id: int | None = None,
    username: str | None = None,
    resource: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    details: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action,
        resource=resource,
        resource_id=resource_id,
        ip_address=ip_address,
        details=sanitize_details(details),
    )
    repository = AuditRepository(session)
    stored = repository.add(entry, commit=commit)
    logger.info(
        "%s | user=%s | resource=%s/%s | ip=%s",
        action,
        username or user_id or "-",
        resource or "-",
        resource_id or "-",
        ip_address or "-",
    )
    return stored


def list_events(
    session: Session,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    user_id: int | None = None,
) -> list[AuditLog]:
    return AuditRepository(session).list_entries(
        limit=limit, offset=offset, action=action, user_id=user_id
    )
