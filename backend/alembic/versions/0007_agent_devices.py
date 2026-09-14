"""Add per-device agent enrollment

Revision ID: 0007_agent_devices
Revises: 0006_add_baseline_source_dataset
Create Date: 2026-09-14

Replaces the previous arrangement where an endpoint agent authenticated with
a short-lived *user* access token.  Each device now holds its own credential
that can be revoked individually, and the agent no longer stops working when
a 30-minute token expires.

Adds:
  - the agents:manage permission (enroll / rotate / revoke)
  - agent_devices — one row per enrolled endpoint.  Only a SHA-256 digest of
    the credential secret is stored; the plaintext key_reference is the
    lookup handle.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007_agent_devices"
down_revision: Union[str, None] = "0006_add_baseline_source_dataset"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New permission ───────────────────────────────────────
    op.execute("ALTER TYPE permissionname ADD VALUE IF NOT EXISTS 'agents:manage'")

    # ── agent_devices ────────────────────────────────────────
    op.create_table(
        "agent_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        # Plaintext lookup handle for the credential.
        sa.Column("key_reference", sa.String(length=64), nullable=False),
        # SHA-256 hex digest of the secret half. The secret itself is shown
        # once at enrollment and is not recoverable.
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_agent_devices_device_id"),
        sa.UniqueConstraint("key_reference", name="uq_agent_devices_key_reference"),
    )
    op.create_index(
        "ix_agent_devices_device_id", "agent_devices", ["device_id"], unique=False
    )
    op.create_index(
        "ix_agent_devices_key_reference",
        "agent_devices",
        ["key_reference"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_agent_devices_key_reference", table_name="agent_devices")
    op.drop_index("ix_agent_devices_device_id", table_name="agent_devices")
    op.drop_table("agent_devices")
    # Postgres cannot remove an enum value in place; agents:manage remains
    # in the permissionname type (consistent with migrations 0003 and 0004).
