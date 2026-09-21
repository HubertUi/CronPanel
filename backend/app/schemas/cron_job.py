"""Pydantic schemas for CronJobs: input, response, status and validation.

CronJobCreate/CronJobUpdate accept a 5-field `schedule_expression`; the
expression is validated and normalized here (single source of truth). The
five derived fields (`minute`, `hour`, ...) are populated from it and should
never be sent by the client.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.cron_validator import CronValidationError, validate_cron_expression

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 200
COMMAND_MAX_LENGTH = 2000
DESCRIPTION_MAX_LENGTH = 2000
EXPRESSION_MAX_LENGTH = 100


def normalize_expression(value: str) -> str:
    result = validate_cron_expression(value)
    if not result.valid:
        message = result.error_message or "Expresión cron inválida."
        raise ValueError(f"{message}")
    if result.normalized_expression is not None:
        return result.normalized_expression
    raise ValueError("Expresión cron inválida.")


class CronJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    command: str = Field(min_length=1, max_length=COMMAND_MAX_LENGTH)
    schedule_expression: str = Field(min_length=1, max_length=EXPRESSION_MAX_LENGTH)
    script_id: int | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El nombre no puede estar vacío.")
        return value.strip()

    @field_validator("command")
    @classmethod
    def command_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("El comando no puede estar vacío.")
        return value.strip()

    @field_validator("schedule_expression")
    @classmethod
    def expression_must_be_valid(cls, value: str) -> str:
        return normalize_expression(value)


class CronJobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    command: str | None = Field(default=None, min_length=1, max_length=COMMAND_MAX_LENGTH)
    schedule_expression: str | None = Field(
        default=None, min_length=1, max_length=EXPRESSION_MAX_LENGTH
    )
    script_id: int | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("El nombre no puede estar vacío.")
        return value.strip() if value is not None else None

    @field_validator("command")
    @classmethod
    def command_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("El comando no puede estar vacío.")
        return value.strip() if value is not None else None

    @field_validator("schedule_expression")
    @classmethod
    def expression_must_be_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_expression(value)


class CronJobStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class CronJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    command: str
    schedule_expression: str
    minute: str
    hour: str
    day_of_month: str
    month: str
    day_of_week: str
    human_description: str
    is_active: bool
    owner_id: int
    script_id: int | None = None
    script_name: str | None = None
    # Phase 5: real values when available (computed from the scheduler and the
    # last persisted execution); None when they cannot be known for sure.
    next_run_at: datetime | None = None
    last_execution_status: str | None = None
    last_execution_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CronJobHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cron_job_id: int
    username: str | None
    action: str
    changes: dict | None = None
    timestamp: datetime


class CronValidateRequest(BaseModel):
    schedule_expression: str = Field(min_length=1, max_length=EXPRESSION_MAX_LENGTH)


class CronValidateResponse(BaseModel):
    valid: bool
    normalized_expression: str | None = None
    fields: list[str] | None = None
    description: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    error_field: str | None = None