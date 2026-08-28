"""Data access for the audit trail."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: AuditLog, commit: bool = True) -> AuditLog:
        self.session.add(entry)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return entry

    def list_entries(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        user_id: int | None = None,
    ) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.timestamp.desc())
        if action is not None:
            statement = statement.where(AuditLog.action == action)
        if user_id is not None:
            statement = statement.where(AuditLog.user_id == user_id)
        statement = statement.limit(limit).offset(offset)
        return list(self.session.execute(statement).scalars())

    def count(self) -> int:
        return self.session.query(AuditLog).count()
