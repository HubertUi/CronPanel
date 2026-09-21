"""Scheduler status schema (Phase 5)."""

from datetime import datetime

from pydantic import BaseModel


class SchedulerStatusResponse(BaseModel):
    running: bool
    jobs_registered: int
    last_sync: datetime | None = None
    timezone: str
    misfire_grace_seconds: int