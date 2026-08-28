"""User-facing response and input schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.permissions import ROLE_PERMISSIONS


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class MeResponse(UserResponse):
    permissions: list[str]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    role: str = Field(..., max_length=50)

    @field_validator("role")
    @classmethod
    def role_must_exist(cls, value: str) -> str:
        if value not in ROLE_PERMISSIONS:
            raise ValueError(f"Rol '{value}' no es válido.")
        return value


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str | None = Field(default=None, min_length=5, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=128)
    role: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def role_must_exist(cls, value: str | None) -> str | None:
        if value is not None and value not in ROLE_PERMISSIONS:
            raise ValueError(f"Rol '{value}' no es válido.")
        return value
