"""Record who performed administrative account changes

Revision ID: 0008_admin_audit_details
Revises: 0007_agent_devices
Create Date: 2026-09-14

User and role management writes audit rows for role changes and for
disabling / enabling accounts. The existing auth_audit_log table only knew
the affected user, so it could not say who made a change or what changed.

Adds (both nullable, so existing rows are untouched):
  - actor_user_id: the administrator who performed the action
  - details:       human-readable description, e.g. "roles: VIEWER -> SECURITY_ANALYST"
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008_admin_audit_details"
down_revision: Union[str, None] = "0007_agent_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auth_audit_log",
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("auth_audit_log", sa.Column("details", sa.Text(), nullable=True))
    op.create_index(
        "ix_auth_audit_log_actor_user_id", "auth_audit_log", ["actor_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_auth_audit_log_actor_user_id", table_name="auth_audit_log")
    op.drop_column("auth_audit_log", "details")
    op.drop_column("auth_audit_log", "actor_user_id")
