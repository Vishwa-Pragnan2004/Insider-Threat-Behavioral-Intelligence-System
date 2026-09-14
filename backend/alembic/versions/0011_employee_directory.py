"""Employee directory: employees, their accounts and devices

Revision ID: 0011_employee_directory
Revises: 0010_access_requests
Create Date: 2026-09-14

Links monitored accounts and devices to employees (ID, department, role,
manager), so events are attributed to people and detection knows who is
privileged and who owns which machine.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_employee_directory"
down_revision: Union[str, None] = "0010_access_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for permission in ("employees:read", "employees:manage"):
        op.execute(f"ALTER TYPE permissionname ADD VALUE IF NOT EXISTS '{permission}'")

    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("job_title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("team", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("manager_employee_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("privileged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", name="uq_employees_employee_id"),
    )
    op.create_index("ix_employees_employee_id", "employees", ["employee_id"])
    op.create_index("ix_employees_status", "employees", ["status"])

    op.create_table(
        "employee_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account", sa.String(length=255), nullable=False),
        sa.Column("account_key", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["employee_uuid"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_key", name="uq_employee_accounts_account_key"),
    )
    op.create_index("ix_employee_accounts_employee_uuid", "employee_accounts", ["employee_uuid"])
    op.create_index("ix_employee_accounts_account_key", "employee_accounts", ["account_key"])

    op.create_table(
        "employee_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=False),
        sa.Column("dedicated", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["employee_uuid"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("device_id", name="uq_employee_devices_device_id"),
    )
    op.create_index("ix_employee_devices_employee_uuid", "employee_devices", ["employee_uuid"])
    op.create_index("ix_employee_devices_device_id", "employee_devices", ["device_id"])


def downgrade() -> None:
    op.drop_table("employee_devices")
    op.drop_table("employee_accounts")
    op.drop_table("employees")
