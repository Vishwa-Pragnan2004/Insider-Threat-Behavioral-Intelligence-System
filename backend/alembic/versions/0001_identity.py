"""Add identity models

Revision ID: 0001_identity
Revises: 
Create Date: 2026-08-20

Tables created:
- permissions
- roles
- permissions (seeded by application seeders at runtime)
- role_permissions (M2M)
- users
- user_roles (M2M)
- auth_audit_log
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_identity"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── permissions ──────────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "name",
            sa.Enum(
                "users:read", "users:create", "users:update", "users:delete",
                "alerts:read", "alerts:create", "alerts:update",
                "investigations:read", "investigations:create", "investigations:update",
                "reports:read", "reports:create",
                "admin:read", "admin:write",
                name="permissionname",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ── roles ────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "name",
            sa.Enum(
                "ADMIN", "SECURITY_ANALYST", "INVESTIGATOR", "VIEWER",
                name="rolename",
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ── role_permissions (M2M) ───────────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # ── users ────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    # ── user_roles (M2M) ─────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )

    # ── auth_audit_log ───────────────────────────────────────────
    op.create_table(
        "auth_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=50), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auth_audit_log_event_type"), "auth_audit_log", ["event_type"]
    )
    op.create_index(
        op.f("ix_auth_audit_log_occurred_at"), "auth_audit_log", ["occurred_at"]
    )
    op.create_index(
        op.f("ix_auth_audit_log_user_id"), "auth_audit_log", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_audit_log_user_id"), table_name="auth_audit_log")
    op.drop_index(op.f("ix_auth_audit_log_occurred_at"), table_name="auth_audit_log")
    op.drop_index(op.f("ix_auth_audit_log_event_type"), table_name="auth_audit_log")
    op.drop_table("auth_audit_log")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("role_permissions")
    op.drop_table("roles")
    op.drop_table("permissions")
    op.execute("DROP TYPE IF EXISTS rolename")
    op.execute("DROP TYPE IF EXISTS permissionname")
