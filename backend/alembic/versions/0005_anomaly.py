"""Add anomaly detection permissions

Revision ID: 0005_anomaly
Revises: 0004_behavioral
Create Date: 2026-09-02

Adds the anomaly:read and anomaly:create permissions to the
permissionname enum so the new /api/v1/anomaly endpoints can be
gated by RBAC.

The anomaly module stores its detection results in MongoDB
(anomaly_results collection), so no additional SQL tables are
required in this migration.
"""
from alembic import op
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0005_anomaly"
down_revision: Union[str, None] = "0004_behavioral"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE permissionname ADD VALUE IF NOT EXISTS 'anomaly:read'")
    op.execute("ALTER TYPE permissionname ADD VALUE IF NOT EXISTS 'anomaly:create'")


def downgrade() -> None:
    # Postgres doesn't support removing enum values in place; permissions remain.
    pass
