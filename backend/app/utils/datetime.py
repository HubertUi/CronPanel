"""Datetime helpers.

SQLite drops timezone information on round-trip, so comparisons must
normalize naive values as UTC before comparing with JWT `iat`/`exp`
(always tz-aware when decoded by PyJWT).
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
