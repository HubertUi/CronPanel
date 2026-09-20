"""Data access for Scripts and Executions. Keeps SQL out of services."""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.cron_job import CronJob
from app.models.execution import Execution
from app.models.script import Script


class ScriptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, script_id: int) -> Script | None:
        statement = select(Script).where(
            Script.id == script_id,
            Script.is_deleted.is_(False),
        )
        return self.session.execute(statement).scalar_one_or_none()

    def get_by_id_include_deleted(self, script_id: int) -> Script | None:
        return self.session.get(Script, script_id)

    def get_by_name(self, name: str) -> Script | None:
        statement = select(Script).where(Script.name == name)
        return self.session.execute(statement).scalar_one_or_none()

    def is_referenced_by_active_job(self, script_id: int) -> bool:
        statement = select(CronJob.id).where(
            CronJob.script_id == script_id,
            CronJob.is_deleted.is_(False),
        )
        return self.session.execute(statement).first() is not None

    def list_scripts(self, *, limit: int = 500) -> list[Script]:
        statement = (
            select(Script)
            .where(Script.is_deleted.is_(False))
            .order_by(Script.id.desc())
            .limit(max(1, min(limit, 500)))
        )
        return list(self.session.execute(statement).scalars())

    def add(self, script: Script, commit: bool = True) -> Script:
        self.session.add(script)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return script


class ExecutionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, execution_id: int) -> Execution | None:
        return self.session.get(Execution, execution_id)

    def add(self, execution: Execution, commit: bool = True) -> Execution:
        self.session.add(execution)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return execution

    def list_owned_job_ids(self, owner_id: int) -> list[int]:
        """Every job (including soft-deleted) owned by a user, used to scope
        the execution history the user is allowed to see."""
        statement = select(CronJob.id).where(CronJob.owner_id == owner_id)
        return list(self.session.execute(statement).scalars())

    def list(
        self,
        *,
        cron_job_ids: list[int] | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Execution]:
        conditions = []
        if cron_job_ids is not None:
            conditions.append(Execution.cron_job_id.in_(cron_job_ids))
        if status:
            conditions.append(Execution.status == status)
        statement = (
            select(Execution)
            .order_by(Execution.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        if conditions:
            statement = statement.where(and_(*conditions))
        return list(self.session.execute(statement).scalars())