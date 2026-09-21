"""Scheduler service: maps CronJob records to APScheduler jobs.

This is the only layer that talks to a scheduling library. It holds no run
logic; when a trigger fires it simply invokes
:func:`app.scheduler.jobs.run_scheduled_job`, which re-reads the database and
delegates to the Phase 4 execution service.

Guarantees (Phase 5 design):
- One APScheduler job per CronJob, identified by ``cronpanel:cron_job:<id>``
  (stable id, ``replace_existing=True`` -> never duplicated).
- ``max_instances=1`` + the ``jobs`` pre-check keep two simultaneous runs of
  the same CronJob impossible.
- ``coalesce=True`` + a bounded ``misfire_grace_time``: a container restart
  never produces a flood of backfilled executions.
- At boot only schedules are registered; nothing runs until its next valid
  occurrence.
- The database is the source of truth: ``sync_from_db()`` reconciles at
  startup and periodically, and is also the mechanism every record change
  goes through (via ``app.scheduler.registry``).
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.core.logging import get_logger
from app.database.database import SessionLocal
from app.repositories.cron_job_repository import CronJobRepository
from app.scheduler.jobs import run_scheduled_job
from app.utils.cron_validator import CronValidationError, validate_cron_expression
from app.utils.datetime import utc_now

logger = get_logger("scheduler")

JOB_ID_PREFIX = "cronpanel:cron_job"
RESYNC_JOB_ID = "cronpanel:resync"


def job_id_for(cron_job_id: int) -> str:
    """Stable scheduler identifier for a CronJob (logical id, never a name)."""
    return f"{JOB_ID_PREFIX}:{cron_job_id}"


class CronScheduler:
    def __init__(self) -> None:
        # Propagate APScheduler records through the project logger config.
        apscheduler_logger = logging.getLogger("apscheduler")
        apscheduler_logger.propagate = True

        self._scheduler = BackgroundScheduler(timezone=settings.SCHEDULER_TIMEZONE)
        self._misfire_grace = settings.SCHEDULER_MISFIRE_GRACE_SECONDS
        self._sync_interval = settings.SCHEDULER_SYNC_INTERVAL_SECONDS
        self._last_sync: datetime | None = None

    # -- lifecycle ----------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._scheduler.running

    @property
    def timezone(self) -> str:
        return str(self._scheduler.timezone)

    @property
    def last_sync(self) -> datetime | None:
        return self._last_sync

    def start(self) -> None:
        if self._scheduler.running:
            return
        self._scheduler.start()
        self.sync_from_db()
        self._scheduler.add_job(
            self.sync_from_db,
            trigger=IntervalTrigger(seconds=self._sync_interval),
            id=RESYNC_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=self._misfire_grace,
        )
        logger.info(
            "Scheduler started: tz=%s, misfire_grace=%ss, sync_interval=%ss.",
            self.timezone,
            self._misfire_grace,
            self._sync_interval,
        )

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    # -- job mapping --------------------------------------------------------

    def job_ids(self) -> set[str]:
        return {job.id for job in self._scheduler.get_jobs()}

    def _armed_job_ids(self) -> set[str]:
        return {
            job_id for job_id in self.job_ids() if job_id.startswith(f"{JOB_ID_PREFIX}:")
        }

    def armed_count(self) -> int:
        """Number of CronJobs currently armed (excludes internal jobs)."""
        return len(self._armed_job_ids())

    def add_or_replace(self, cron_job_id: int, schedule_expression: str) -> bool:
        """Register (or update in place) the schedule for a CronJob.

        Returns ``True`` when armed; ``False`` when the stored expression
        cannot be honored (logged, the DB keeps the task active and the next
        resync retries). Never creates a second job for the same CronJob.
        """
        result = validate_cron_expression(schedule_expression)
        if not result.valid or result.normalized_expression is None:
            logger.error(
                "Cron job %s has an unschedulable expression; skipped (%s).",
                cron_job_id,
                result.error_code,
            )
            return False

        try:
            trigger = CronTrigger.from_crontab(
                result.normalized_expression,
                timezone=settings.SCHEDULER_TIMEZONE,
            )
        except (ValueError, CronValidationError):
            logger.exception(
                "Cron job %s expression could not be scheduled; skipped.", cron_job_id
            )
            return False

        self._scheduler.add_job(
            run_scheduled_job,
            trigger=trigger,
            id=job_id_for(cron_job_id),
            args=[cron_job_id],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=self._misfire_grace,
        )
        return True

    def remove(self, cron_job_id: int) -> None:
        self._scheduler.remove_job(job_id_for(cron_job_id))

    def next_run(self, cron_job_id: int) -> datetime | None:
        """Next fire time in the configured schedule; ``None`` when the job
        is not armed (paused, deleted, disabled script, or scheduler off)."""
        job = self._scheduler.get_job(job_id_for(cron_job_id))
        return job.next_run_time if job is not None else None

    # -- sync ---------------------------------------------------------------

    def sync_from_db(self) -> int:
        """Reconcile armed jobs with the database (source of truth).

        Register every eligible CronJob, drop any armed job that is no longer
        eligible. Returns the number of eligible jobs registered.
        """
        if not self._scheduler.running:
            return 0

        with SessionLocal() as session:
            eligible = CronJobRepository(session).list_eligible_for_scheduling()

        desired_ids: set[str] = set()
        for job in eligible:
            self.add_or_replace(job.id, job.schedule_expression)
            desired_ids.add(job_id_for(job.id))

        for armed in self._armed_job_ids() - desired_ids:
            try:
                self._scheduler.remove_job(armed)
            except Exception:  # noqa: BLE001
                logger.warning("Could not remove stale scheduler job %s.", armed)

        self._last_sync = utc_now()
        logger.info("Scheduler sync: %s cron job(s) armed.", len(eligible))
        return len(eligible)

    def add_or_replace_from_db(self, cron_job_id: int) -> bool:
        """Re-arm one job straight from the DB (used after record changes).

        Re-checks eligibility from the database instead of trusting caller
        state, then arms or removes accordingly.
        """
        with SessionLocal() as session:
            job = CronJobRepository(session).get_by_id(cron_job_id)
            if job is None or not job.is_active:
                self.remove_if_armed(cron_job_id)
                return False
            if job.id not in {item.id for item in CronJobRepository(session).list_eligible_for_scheduling()}:
                self.remove_if_armed(cron_job_id)
                return False
            expression = job.schedule_expression
        return self.add_or_replace(cron_job_id, expression)

    def remove_if_armed(self, cron_job_id: int) -> None:
        try:
            self._scheduler.remove_job(job_id_for(cron_job_id))
        except Exception:  # noqa: BLE001 - not armed is fine
            pass