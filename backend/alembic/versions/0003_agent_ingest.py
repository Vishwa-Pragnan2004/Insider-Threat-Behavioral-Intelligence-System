"""Add agent:ingest permission

Revision ID: 0003_agent_ingest
Revises: 0002_activity
Create Date: 2026-08-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_agent_ingest"
down_revision: Union[str, None] = "0002_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new value to the permissionname enum type (Postgres).
    op.execute("ALTER TYPE permissionname ADD VALUE IF NOT EXISTS 'agent:ingest'")


def downgrade() -> None:
    # Postgres does not support removing an enum value in place; this is a
    # no-op downgrade. The value remains in the enum type.
    pass
