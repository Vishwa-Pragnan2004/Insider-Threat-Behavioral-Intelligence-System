"""Add source_dataset to behavioral_baselines

Revision ID: 0006_add_baseline_source_dataset
Revises: 0005_anomaly
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_baseline_source_dataset"
down_revision: Union[str, None] = "0005_anomaly"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "behavioral_baselines",
        sa.Column("source_dataset", sa.String(length=64), nullable=False, server_default="all"),
    )


def downgrade() -> None:
    op.drop_column("behavioral_baselines", "source_dataset")
