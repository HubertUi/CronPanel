"""User model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.datetime import utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Session invalidation threshold: tokens issued before this moment are
    # rejected (used on password change, deactivation and role changes).
    tokens_invalid_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    role = relationship("Role", back_populates="users")
    cron_jobs = relationship("CronJob", back_populates="owner")
    scripts = relationship("Script", back_populates="creator")

    @property
    def role_name(self) -> str:
        return self.role.name if self.role else ""

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} active={self.is_active}>"
