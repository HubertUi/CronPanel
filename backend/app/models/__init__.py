"""Model imports so that `Base.metadata` is fully populated.

Alembic (env.py) and create_all rely on this module being imported.
"""

from app.models.audit_log import AuditLog
from app.models.cron_job import CronJob
from app.models.cron_job_history import CronJobHistory
from app.models.revoked_token import RevokedToken
from app.models.role import Role
from app.models.user import User

__all__ = [
    "AuditLog",
    "CronJob",
    "CronJobHistory",
    "RevokedToken",
    "Role",
    "User",
]