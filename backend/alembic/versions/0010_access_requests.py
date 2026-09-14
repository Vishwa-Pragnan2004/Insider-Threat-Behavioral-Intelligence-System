"""Access requests: self-service account requests awaiting approval

Revision ID: 0010_access_requests
Revises: 0009_soc_roles_and_dashboards
Create Date: 2026-09-14

People ask for an account and the role they need from the sign-in page. The
account is created disabled; an administrator approves (granting roles) or
rejects the request.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_access_requests"
down_revision: Union[str, None] = "0009_soc_roles_and_dashboards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("granted_roles", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_access_requests_user_id", "access_requests", ["user_id"])
    op.create_index("ix_access_requests_status", "access_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_access_requests_status", table_name="access_requests")
    op.drop_index("ix_access_requests_user_id", table_name="access_requests")
    op.drop_table("access_requests")
