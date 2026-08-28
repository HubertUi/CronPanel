"""Data access for CronJobs. Keeps SQL out of services and routes."""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.cron_job import CronJob
from app.models.cron_job_history import CronJobHistory


class CronJobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, cron_job_id: int) -> CronJob | None:
        statement = select(CronJob).where(
            CronJob.id == cron_job_id,
            CronJob.is_deleted.is_(False),
        )
        return self.session.execute(statement).scalar_one_or_none()

    def get_by_id_include_deleted(self, cron_job_id: int) -> CronJob | None:
        """Fetch a job regardless of the soft-delete flag (for history)."""
        return self.session.get(CronJob, cron_job_id)

    def list_jobs(
        self,
        *,
        owner_id: int | None = None,
        is_active: bool | None = None,
        name: str | None = None,
        schedule: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CronJob]:
        conditions = [CronJob.is_deleted.is_(False)]
        if owner_id is not None:
            conditions.append(CronJob.owner_id == owner_id)
        if is_active is not None:
            conditions.append(CronJob.is_active.is_(is_active))
        if name:
            conditions.append(CronJob.name.ilike(f"%{name}%"))
        if schedule:
            conditions.append(CronJob.schedule_expression == schedule)

        statement = (
            select(CronJob)
            .where(and_(*conditions))
            .order_by(CronJob.id.desc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return list(self.session.execute(statement).scalars())

    def add(self, cron_job: CronJob, commit: bool = True) -> CronJob:
        self.session.add(cron_job)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return cron_job

    def commit(self) -> None:
        self.session.commit()


class CronJobHistoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: CronJobHistory, commit: bool = True) -> CronJobHistory:
        self.session.add(entry)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return entry

    def list_for_job(
        self,
        cron_job_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CronJobHistory]:
        statement = (
            select(CronJobHistory)
            .where(CronJobHistory.cron_job_id == cron_job_id)
            .order_by(CronJobHistory.id.asc())
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        )
        return list(self.session.execute(statement).scalars())

    def count_for_job(self, cron_job_id: int) -> int:
        statement = select(CronJobHistory.id).where(
            CronJobHistory.cron_job_id == cron_job_id
        )
        return len(list(self.session.execute(statement).scalars()))