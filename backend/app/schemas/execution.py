"""Pydantic schemas for Executions (Phase 4)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cron_job_id: int | None
    cron_job_name: str | None = None
    script_id: int | None
    script_name: str | None = None
    trigger: str
    status: str
    exit_code: int | None
    stdout: str | None
    stderr: str | None
    error: str | None
    duration_ms: int | None
    username: str | None
    ip_address: str | None
    started_at: datetime
    finished_at: datetime | None