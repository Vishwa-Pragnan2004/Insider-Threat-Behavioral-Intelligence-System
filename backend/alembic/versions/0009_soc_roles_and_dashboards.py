"""Add the SOC Engineer and Security Manager roles and role dashboard permissions

Revision ID: 0009_soc_roles_and_dashboards
Revises: 0008_admin_audit_details
Create Date: 2026-09-14

Role and permission names are Postgres enum types, so new values must be added
to the types before the startup seeder can create the roles. The seeder then
creates SOC_ENGINEER and SECURITY_MANAGER and grants the dashboard permissions.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_soc_roles_and_dashboards"
down_revision: Union[str, None] = "0008_admin_audit_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'SOC_ENGINEER'")
    op.execute("ALTER TYPE rolename ADD VALUE IF NOT EXISTS 'SECURITY_MANAGER'")
    for permission in ("dashboard:analyst", "dashboard:soc", "dashboard:manager"):
        op.execute(f"ALTER TYPE permissionname ADD VALUE IF NOT EXISTS '{permission}'")


def downgrade() -> None:
    # Postgres can't remove a value from an enum type; the values are harmless
    # if unused, so a downgrade leaves them in place.
    pass
