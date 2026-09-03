"""Add activity ingestion models

Revision ID: 0002_activity
Revises: 0001_identity
Create Date: 2026-08-30

Tables created:
- ingestion_jobs    : one row per dataset upload/ingestion run
- ingestion_errors  : per-row failures captured during ingestion
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_activity"
down_revision: Union[str, None] = "0001_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ingestion_jobs ─────────────────────────────────────────
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column(
            "log_type",
            sa.Enum(
                "logon", "device", "file", "email",
                "http", "ldap", "psychometric", "unknown",
                name="logtype",
            ),
            nullable=False,
        ),
        sa.Column("source_dataset", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "completed", "failed", "partial",
                name="jobstatus",
            ),
            nullable=False,
        ),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_stored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("initiated_by", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingestion_jobs_status"), "ingestion_jobs", ["status"]
    )
    op.create_index(
        op.f("ix_ingestion_jobs_log_type"), "ingestion_jobs", ["log_type"]
    )
    op.create_index(
        op.f("ix_ingestion_jobs_created_at"), "ingestion_jobs", ["created_at"]
    )

    # ── ingestion_errors ───────────────────────────────────────
    op.create_table(
        "ingestion_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["ingestion_jobs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ingestion_errors_job_id"),
        "ingestion_errors",
        ["job_id"],
    )
    op.create_index(
        op.f("ix_ingestion_errors_occurred_at"),
        "ingestion_errors",
        ["occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ingestion_errors_occurred_at"), table_name="ingestion_errors")
    op.drop_index(op.f("ix_ingestion_errors_job_id"), table_name="ingestion_errors")
    op.drop_table("ingestion_errors")
    op.drop_index(op.f("ix_ingestion_jobs_created_at"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_log_type"), table_name="ingestion_jobs")
    op.drop_index(op.f("ix_ingestion_jobs_status"), table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS logtype")
