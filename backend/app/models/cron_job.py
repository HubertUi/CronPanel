"""CronJob model.

A CronJob represents a scheduled task as *data* managed by CronPanel.

IMPORTANT (Phase 3 scope):
The `command` field is only stored metadata. CronPanel Phase 3 does NOT
execute it, does not touch the system crontab, and does not run any shell
command. Real execution happens in a later phase.

Scheduling model (single source of truth):
- `schedule_expression` is the canonical representation (5-field cron).
- `minute`, `hour`, `day_of_month`, `month`, `day_of_week` are derived
  from the expression and kept in sync by the service on every write.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.datetime import utc_now


class CronJob(Base):
    __tablename__ = "cron_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)

    schedule_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    minute: Mapped[str] = mapped_column(String(20), nullable=False)
    hour: Mapped[str] = mapped_column(String(20), nullable=False)
    day_of_month: Mapped[str] = mapped_column(String(20), nullable=False)
    month: Mapped[str] = mapped_column(String(20), nullable=False)
    day_of_week: Mapped[str] = mapped_column(String(20), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # Soft-delete flag: the row (and its history) is preserved after DELETE.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    owner = relationship("User", back_populates="cron_jobs")
    history = relationship(
        "CronJobHistory",
        back_populates="cron_job",
        cascade="all, delete-orphan",
        order_by="CronJobHistory.id",
    )

    def __repr__(self) -> str:
        return f"<CronJob id={self.id} name={self.name!r} active={self.is_active}>"