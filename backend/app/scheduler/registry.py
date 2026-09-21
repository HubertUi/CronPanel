"""Process-wide scheduler holder and notification helpers.

The scheduler is a singleton created in the FastAPI lifespan. Business and
transport layers notify it through these functions after a successful commit
so schedule changes take effect immediately (no restart required). When the
scheduler is disabled or not started, every call degrades to a harmless
no-op: the database remains the source of truth and the next sync reconciles.
"""

from app.core.logging import get_logger
from app.scheduler.service import CronScheduler

logger = get_logger("scheduler.registry")

_scheduler: CronScheduler | None = None


def bind(scheduler: CronScheduler | None) -> None:
    global _scheduler
    _scheduler = scheduler


def get_scheduler() -> CronScheduler | None:
    return _scheduler


def is_running() -> bool:
    scheduler = _scheduler
    return scheduler is not None and scheduler.running


def notify_job_changed(cron_job_id: int) -> None:
    """Call after a CronJob was created, edited or (re)activated."""

    if not is_running():
        return
    _scheduler.add_or_replace_from_db(cron_job_id)


def notify_job_removed(cron_job_id: int) -> None:
    """Call after a CronJob was paused or deleted."""

    if not is_running():
        return
    _scheduler.remove_if_armed(cron_job_id)


def resync() -> None:
    """Reconcile everything with the database (used e.g. after script edits)."""

    if not is_running():
        return
    _scheduler.sync_from_db()
    logger.debug("Full scheduler resync requested.")