"""Scheduler admin endpoints (Phase 5).

Read-only status inspection. There is deliberately NO mutation endpoint:
schedules change through the cron-job/script resources, never through a
public 'add arbitrary job' hole.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import require_permissions
from app.core.config import settings
from app.core.permissions import Permission
from app.models.user import User
from app.scheduler.registry import get_scheduler
from app.schemas.scheduler import SchedulerStatusResponse

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status", response_model=SchedulerStatusResponse)
def scheduler_status(
    current_user: User = Depends(require_permissions(Permission.SCHEDULER_READ)),
) -> SchedulerStatusResponse:
    scheduler = get_scheduler()
    if scheduler is None or not scheduler.running:
        return SchedulerStatusResponse(
            running=False,
            jobs_registered=0,
            last_sync=None,
            timezone=settings.SCHEDULER_TIMEZONE,
            misfire_grace_seconds=settings.SCHEDULER_MISFIRE_GRACE_SECONDS,
        )
    return SchedulerStatusResponse(
        running=True,
        jobs_registered=scheduler.armed_count(),
        last_sync=scheduler.last_sync,
        timezone=scheduler.timezone,
        misfire_grace_seconds=settings.SCHEDULER_MISFIRE_GRACE_SECONDS,
    )