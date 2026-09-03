"""
ITBIS — Identity Module: Enums
Role names and permission names used throughout the identity module.
"""

from enum import Enum


class RoleName(str, Enum):
    """System roles for RBAC."""

    ADMIN = "ADMIN"
    SECURITY_ANALYST = "SECURITY_ANALYST"
    INVESTIGATOR = "INVESTIGATOR"
    VIEWER = "VIEWER"


class PermissionName(str, Enum):
    """
    Granular permissions assigned to roles.
    Format: <resource>:<action>
    """

    # Users
    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_DELETE = "users:delete"

    # Alerts
    ALERTS_READ = "alerts:read"
    ALERTS_CREATE = "alerts:create"
    ALERTS_UPDATE = "alerts:update"

    # Investigations
    INVESTIGATIONS_READ = "investigations:read"
    INVESTIGATIONS_CREATE = "investigations:create"
    INVESTIGATIONS_UPDATE = "investigations:update"

    # Reports
    REPORTS_READ = "reports:read"
    REPORTS_CREATE = "reports:create"

    # Admin
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"

    # Agent (Phase 3)
    AGENT_INGEST = "agent:ingest"

    # Behavioral features (Phase 4)
    BEHAVIORAL_READ = "behavioral:read"
    BEHAVIORAL_CREATE = "behavioral:create"

    # Anomaly detection (Phase 5)
    ANOMALY_READ = "anomaly:read"
    ANOMALY_CREATE = "anomaly:create"


# ─── Role → Permission Map ───────────────────────────────────
ROLE_PERMISSIONS: dict[RoleName, list[PermissionName]] = {
    RoleName.ADMIN: list(PermissionName),  # All permissions

    RoleName.SECURITY_ANALYST: [
        PermissionName.USERS_READ,
        PermissionName.ALERTS_READ,
        PermissionName.ALERTS_CREATE,
        PermissionName.ALERTS_UPDATE,
        PermissionName.INVESTIGATIONS_READ,
        PermissionName.INVESTIGATIONS_CREATE,
        PermissionName.INVESTIGATIONS_UPDATE,
        PermissionName.REPORTS_READ,
        PermissionName.REPORTS_CREATE,
        PermissionName.ADMIN_READ,
        PermissionName.AGENT_INGEST,
        PermissionName.BEHAVIORAL_READ,
        PermissionName.BEHAVIORAL_CREATE,
        PermissionName.ANOMALY_READ,
        PermissionName.ANOMALY_CREATE,
    ],

    RoleName.INVESTIGATOR: [
        PermissionName.USERS_READ,
        PermissionName.ALERTS_READ,
        PermissionName.INVESTIGATIONS_READ,
        PermissionName.INVESTIGATIONS_CREATE,
        PermissionName.INVESTIGATIONS_UPDATE,
        PermissionName.REPORTS_READ,
        PermissionName.BEHAVIORAL_READ,
        PermissionName.ANOMALY_READ,
    ],

    RoleName.VIEWER: [
        PermissionName.USERS_READ,
        PermissionName.ALERTS_READ,
        PermissionName.INVESTIGATIONS_READ,
        PermissionName.REPORTS_READ,
        PermissionName.BEHAVIORAL_READ,
        PermissionName.ANOMALY_READ,
    ],
}
