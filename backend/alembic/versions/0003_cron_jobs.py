"""Phase 3 tables: cron_jobs and cron_job_history.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cron_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("schedule_expression", sa.String(100), nullable=False),
        sa.Column("minute", sa.String(20), nullable=False),
        sa.Column("hour", sa.String(20), nullable=False),
        sa.Column("day_of_month", sa.String(20), nullable=False),
        sa.Column("month", sa.String(20), nullable=False),
        sa.Column("day_of_week", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cron_jobs_name", "cron_jobs", ["name"])
    op.create_index("ix_cron_jobs_owner_id", "cron_jobs", ["owner_id"])
    op.create_index("ix_cron_jobs_is_active", "cron_jobs", ["is_active"])
    op.create_index("ix_cron_jobs_is_deleted", "cron_jobs", ["is_deleted"])

    op.create_table(
        "cron_job_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cron_job_id",
            sa.Integer(),
            sa.ForeignKey("cron_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changes", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cron_job_history_cron_job_id", "cron_job_history", ["cron_job_id"])
    op.create_index("ix_cron_job_history_timestamp", "cron_job_history", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_cron_job_history_timestamp", "cron_job_history")
    op.drop_index("ix_cron_job_history_cron_job_id", "cron_job_history")
    op.drop_table("cron_job_history")

    op.drop_index("ix_cron_jobs_is_deleted", "cron_jobs")
    op.drop_index("ix_cron_jobs_is_active", "cron_jobs")
    op.drop_index("ix_cron_jobs_owner_id", "cron_jobs")
    op.drop_index("ix_cron_jobs_name", "cron_jobs")
    op.drop_table("cron_jobs")