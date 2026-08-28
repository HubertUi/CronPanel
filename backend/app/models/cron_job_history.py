"""CronJobHistory model.

Per-job change history. Records what happened to a CronJob and by whom,
with a JSON snapshot of the relevant changes. This complements the global
audit trail (`AuditLog`): history is scoped to a single job, audit is the
cross-cutting security trail. Never store secrets, passwords or tokens.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.datetime import utc_now


class CronJobHistory(Base):
    __tablename__ = "cron_job_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    cron_job_id: Mapped[int] = mapped_column(
        ForeignKey("cron_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Snapshot kept even if the acting user is later deleted.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # One of CREATED / UPDATED / ENABLED / DISABLED / DELETED
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # JSON-encoded diff of the fields that changed (or null).
    changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    cron_job = relationship("CronJob", back_populates="history")

    def __repr__(self) -> str:
        return f"<CronJobHistory id={self.id} job={self.cron_job_id} action={self.action!r}>"