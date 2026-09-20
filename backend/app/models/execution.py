"""Execution model.

One row per run of a CronJob script. Persisted before the process starts
(status ``running``) and finalized afterwards, so a crash mid-run always
leaves a traceable running record.

Output stores the captured ``stdout`` / ``stderr`` (capped by configuration)
plus the exit code, wall-clock duration and outcome. Secrets never reach this
table: the subprocess runs with a minimal environment.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.datetime import utc_now


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    cron_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("cron_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    script_id: Mapped[int | None] = mapped_column(
        ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Trigger that launched this run (always ``manual`` for now).
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # running / success / failed / timed_out
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)

    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Snapshot kept even if the acting user is later deleted.
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cron_job = relationship("CronJob", back_populates="executions")
    script = relationship("Script", back_populates="executions")

    def __repr__(self) -> str:
        return f"<Execution id={self.id} job={self.cron_job_id} status={self.status!r}>"