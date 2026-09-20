"""Script model.

A Script is a file living inside the allow-list directory
(``settings.execution_scripts_dir``) that a CronJob may be bound to. The file
itself is ordinary source code; CronPanel never stores or builds a command
string from a Script.

Only administrators can register scripts (Phase 4). The path is validated by
the execution policy at registration time and again at execution time.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base
from app.utils.datetime import utc_now


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    # Soft-delete flag: the row is preserved so execution history stays intact.
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    creator = relationship("User", back_populates="scripts")
    executions = relationship("Execution", back_populates="script")

    def __repr__(self) -> str:
        return f"<Script id={self.id} name={self.name!r} enabled={self.is_enabled}>"