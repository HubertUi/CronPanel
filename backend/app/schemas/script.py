"""Pydantic schemas for Scripts (Phase 4).

Scripts reference files inside the allow-list directory. The path is
normalized and validated against that boundary by the execution policy at
registration and again at execution time.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 200
DESCRIPTION_MAX_LENGTH = 2000
PATH_MAX_LENGTH = 2000

_NOT_BLANK_MESSAGE = "El valor no puede estar vacío."


class ScriptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    path: str = Field(min_length=1, max_length=PATH_MAX_LENGTH)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(_NOT_BLANK_MESSAGE)
        return value.strip()

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(_NOT_BLANK_MESSAGE)
        return value.strip()


class ScriptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    path: str | None = Field(default=None, min_length=1, max_length=PATH_MAX_LENGTH)
    is_enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError(_NOT_BLANK_MESSAGE)
        return value.strip() if value is not None else None

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError(_NOT_BLANK_MESSAGE)
        return value.strip() if value is not None else None


class ScriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    path: str
    is_enabled: bool
    created_by: int | None
    created_by_username: str | None = None
    created_at: datetime
    updated_at: datetime