"""Analyst verdicts: what each alert turned out to be

Revision ID: 0012_analyst_verdicts
Revises: 0011_employee_directory
Create Date: 2026-09-18

Records an analyst's judgement of an alert (confirmed threat, policy
violation, benign, inconclusive) together with a snapshot of what the
system believed when it raised that alert. These are the labels a
supervised model would later be trained on, and the basis for measuring
the system's precision against real decisions rather than a dataset.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_analyst_verdicts"
down_revision: Union[str, None] = "0011_employee_directory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analyst_verdicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_user_id", sa.String(length=255), nullable=False),
        sa.Column("subject_day", sa.Date(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(length=255), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        # Evidence snapshot.
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("priority", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        sa.Column(
            "detectors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyst_verdicts_alert_id", "analyst_verdicts", ["alert_id"])
    op.create_index(
        "ix_analyst_verdicts_subject_user_id", "analyst_verdicts", ["subject_user_id"]
    )
    op.create_index("ix_analyst_verdicts_subject_day", "analyst_verdicts", ["subject_day"])
    op.create_index("ix_analyst_verdicts_verdict", "analyst_verdicts", ["verdict"])
    op.create_index("ix_analyst_verdicts_decided_by", "analyst_verdicts", ["decided_by"])
    op.create_index(
        "ix_analyst_verdicts_superseded_at", "analyst_verdicts", ["superseded_at"]
    )
    # At most one verdict in force per alert. Partial index, so superseded
    # rows accumulate freely while the current one stays unambiguous.
    op.create_index(
        "uq_analyst_verdicts_current_per_alert",
        "analyst_verdicts",
        ["alert_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_analyst_verdicts_current_per_alert", table_name="analyst_verdicts")
    op.drop_index("ix_analyst_verdicts_superseded_at", table_name="analyst_verdicts")
    op.drop_index("ix_analyst_verdicts_decided_by", table_name="analyst_verdicts")
    op.drop_index("ix_analyst_verdicts_verdict", table_name="analyst_verdicts")
    op.drop_index("ix_analyst_verdicts_subject_day", table_name="analyst_verdicts")
    op.drop_index("ix_analyst_verdicts_subject_user_id", table_name="analyst_verdicts")
    op.drop_index("ix_analyst_verdicts_alert_id", table_name="analyst_verdicts")
    op.drop_table("analyst_verdicts")
