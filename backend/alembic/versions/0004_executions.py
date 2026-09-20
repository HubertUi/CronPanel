"""Phase 4 tables: scripts and executions, plus cron_jobs.script_id.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scripts_name", "scripts", ["name"], unique=True)
    op.create_index("ix_scripts_is_enabled", "scripts", ["is_enabled"])
    op.create_index("ix_scripts_is_deleted", "scripts", ["is_deleted"])
    op.create_index("ix_scripts_created_by", "scripts", ["created_by"])

    op.create_table(
        "executions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cron_job_id",
            sa.Integer(),
            sa.ForeignKey("cron_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "script_id",
            sa.Integer(),
            sa.ForeignKey("scripts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_executions_cron_job_id", "executions", ["cron_job_id"])
    op.create_index("ix_executions_script_id", "executions", ["script_id"])
    op.create_index("ix_executions_status", "executions", ["status"])
    op.create_index("ix_executions_started_at", "executions", ["started_at"])

    with op.batch_alter_table("cron_jobs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "script_id",
                sa.Integer(),
                sa.ForeignKey(
                    "scripts.id",
                    ondelete="SET NULL",
                    name="fk_cron_jobs_script_id_scripts",
                ),
                nullable=True,
            )
        )
        batch_op.create_index("ix_cron_jobs_script_id", ["script_id"])


def downgrade() -> None:
    with op.batch_alter_table("cron_jobs") as batch_op:
        batch_op.drop_index("ix_cron_jobs_script_id")
        batch_op.drop_column("script_id")

    op.drop_index("ix_executions_started_at", "executions")
    op.drop_index("ix_executions_status", "executions")
    op.drop_index("ix_executions_script_id", "executions")
    op.drop_index("ix_executions_cron_job_id", "executions")
    op.drop_table("executions")

    op.drop_index("ix_scripts_created_by", "scripts")
    op.drop_index("ix_scripts_is_deleted", "scripts")
    op.drop_index("ix_scripts_is_enabled", "scripts")
    op.drop_index("ix_scripts_name", "scripts")
    op.drop_table("scripts")