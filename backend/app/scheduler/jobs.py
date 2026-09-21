"""The unit of work APScheduler fires for a CronJob.

It never executes anything itself — no subprocess, no shell, no crontab
touching. It re-validates the job/script state from the database (the
scheduler is not the source of truth), enforces the one-run-at-a-time rule
and delegates the actual run to the Phase 4 execution service.

Skipped runs (already running, script gone, job flipped to inactive) are
recorded in the audit trail so nothing is lost silently.
"""

from app.core import audit_actions as AuditAction
from app.core.execution_status import SYSTEM_ACTOR_USERNAME
from app.core.logging import get_logger
from app.database.database import SessionLocal
from app.models.cron_job import CronJob
from app.repositories.cron_job_repository import CronJobRepository
from app.repositories.execution_repository import ExecutionRepository
from app.services import audit_service, execution_service
from app.services.cron_job_service import CronJobNotFoundError

logger = get_logger("scheduler.jobs")


def _record_skip(session, job: CronJob, reason: str) -> None:
    audit_service.record_event(
        session,
        AuditAction.EXECUTION_SKIPPED,
        user_id=None,
        username=SYSTEM_ACTOR_USERNAME,
        resource="cron_job",
        resource_id=str(job.id),
        details={
            "cron_job_id": job.id,
            "cron_job_name": job.name,
            "reason": reason,
        },
        commit=True,
    )
    logger.info("Cron job %s skipped: %s", job.id, reason)


def run_scheduled_job(cron_job_id: int) -> None:
    """APScheduler callback: decide and delegate one scheduled run."""
    logger.info("Scheduled run due for cron job %s.", cron_job_id)
    with SessionLocal() as session:
        job = CronJobRepository(session).get_by_id(cron_job_id)
        if job is None or not job.is_active:
            # Deleted/paused meanwhile: nothing to do, the fire is discarded.
            logger.info(
                "Scheduled fire for cron job %s ignored (no longer active/scheduled).",
                cron_job_id,
            )
            return

        if ExecutionRepository(session).has_running_execution(cron_job_id):
            _record_skip(
                session,
                job,
                "execution skipped because cron job is already running",
            )
            return

        try:
            execution = execution_service.run_scheduled_cron_job(session, cron_job_id)
            logger.info(
                "Scheduled run of cron job %s -> execution #%s (%s).",
                cron_job_id,
                execution.id,
                execution.status,
            )
        except CronJobNotFoundError:
            _record_skip(session, job, "execution skipped because cron job no longer exists")
        except execution_service.JobInactiveError:
            _record_skip(session, job, "execution skipped because cron job is paused")
        except (
            execution_service.ScriptNotLinkedError,
            execution_service.ScriptUnavailableError,
        ):
            _record_skip(session, job, "execution skipped because the bound script is unavailable")
        except Exception:  # noqa: BLE001
            logger.exception(
                "Scheduled run of cron job %s failed unexpectedly.", cron_job_id
            )