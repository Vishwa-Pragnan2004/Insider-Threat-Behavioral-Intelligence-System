"""Add behavioral features & baselines

Revision ID: 0004_behavioral
Revises: 0003_agent_ingest
Create Date: 2026-08-30

Adds:
  - behavioural permissions to the permissionname enum
  - behavioral_baselines (one row per user) — mean/std of daily features
    computed over a historical window.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_behavioral"
down_revision: Union[str, None] = "0003_agent_ingest"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FEATURE_VERSION = "behavioral_features_v1"


def upgrade() -> None:
    # ── New permissions ──────────────────────────────────────
    op.execute("ALTER TYPE permissionname ADD VALUE IF NOT EXISTS 'behavioral:read'")
    op.execute("ALTER TYPE permissionname ADD VALUE IF NOT EXISTS 'behavioral:create'")

    # ── behavioral_baselines ────────────────────────────────
    op.create_table(
        "behavioral_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("feature_version", sa.String(length=64), nullable=False),
        # Statistics over the historical window.  JSONB keeps the schema
        # open so future feature versions can add new keys without
        # altering the table.
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(
                postgresql.JSONB(), "postgresql"
            ),
            nullable=False,
        ),
        # The historical window the baseline was built from.
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        # How many observation days the baseline is based on.
        sa.Column("observation_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "feature_version", name="uq_behavioral_baseline_user_version"),
    )
    op.create_index(
        op.f("ix_behavioral_baselines_user_id"),
        "behavioral_baselines",
        ["user_id"],
    )
    op.create_index(
        op.f("ix_behavioral_baselines_feature_version"),
        "behavioral_baselines",
        ["feature_version"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_behavioral_baselines_feature_version"), table_name="behavioral_baselines"
    )
    op.drop_index(
        op.f("ix_behavioral_baselines_user_id"), table_name="behavioral_baselines"
    )
    op.drop_table("behavioral_baselines")
    # Postgres doesn't support removing enum values; permissions remain.
