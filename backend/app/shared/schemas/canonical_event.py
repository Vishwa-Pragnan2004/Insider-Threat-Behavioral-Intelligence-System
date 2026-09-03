"""
ITBIS Shared — Canonical Event Schema
The normalised representation of any activity event in the system.
ALL log sources (CERT, Windows, Linux, Cloud, etc.) must produce this schema
after ingestion and parsing. This is the single source of truth for events.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Canonical event types supported by ITBIS."""

    # Authentication
    LOGON = "logon"
    LOGOFF = "logoff"
    LOGON_FAILED = "logon_failed"

    # File Activity
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    FILE_COPY = "file_copy"
    FILE_MOVE = "file_move"
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_PRINT = "file_print"

    # USB / Removable Media
    USB_INSERT = "usb_insert"
    USB_REMOVE = "usb_remove"
    USB_FILE_COPY = "usb_file_copy"

    # Email
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    EMAIL_ATTACHMENT_SENT = "email_attachment_sent"
    EMAIL_EXTERNAL = "email_external"

    # Web / HTTP
    HTTP_REQUEST = "http_request"
    HTTP_UPLOAD = "http_upload"
    HTTP_DOWNLOAD = "http_download"

    # Active Directory / LDAP
    LDAP_QUERY = "ldap_query"
    PRIVILEGE_CHANGE = "privilege_change"
    GROUP_CHANGE = "group_change"
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_DISABLED = "account_disabled"
    PASSWORD_CHANGE = "password_change"

    # Application
    APP_LAUNCH = "app_launch"
    APP_CLOSE = "app_close"
    APP_INSTALL = "app_install"

    # Network
    NETWORK_CONNECTION = "network_connection"
    VPN_CONNECT = "vpn_connect"
    VPN_DISCONNECT = "vpn_disconnect"
    DATA_TRANSFER = "data_transfer"

    # Physical
    BADGE_ACCESS = "badge_access"
    BADGE_DENIED = "badge_denied"

    # System
    POLICY_VIOLATION = "policy_violation"
    SYSTEM_EVENT = "system_event"

    # Unknown / Other
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Risk severity levels."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CanonicalEvent(BaseModel):
    """
    Canonical Event Schema.

    Every activity event in ITBIS, regardless of its source dataset
    (CERT, Windows Event Log, Linux Audit, etc.), must be normalised
    to this schema before entering the processing pipeline.

    This schema is intentionally source-agnostic.
    """

    # ─── Identity ──────────────────────────────────────────
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: EventType
    source_dataset: str = Field(description="Dataset or log source name, e.g. 'cert_r4.2'")
    raw_event_id: Optional[str] = Field(
        default=None,
        description="Original event ID from the source log"
    )

    # ─── Timing ────────────────────────────────────────────
    timestamp: datetime = Field(description="Event timestamp in UTC")
    ingested_at: datetime = Field(
        default_factory=lambda: __import__("datetime").datetime.utcnow(),
        description="When ITBIS ingested this event"
    )

    # ─── Actor ─────────────────────────────────────────────
    user_id: str = Field(description="Internal ITBIS user identifier")
    username: Optional[str] = None
    user_email: Optional[str] = None
    employee_id: Optional[str] = None
    department: Optional[str] = None

    # ─── Asset / Device ────────────────────────────────────
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    operating_system: Optional[str] = None

    # ─── Activity Details ──────────────────────────────────
    target_resource: Optional[str] = Field(
        default=None,
        description="File path, URL, email address, etc."
    )
    target_type: Optional[str] = Field(
        default=None,
        description="'file', 'url', 'email', 'process', etc."
    )
    action: Optional[str] = None
    result: Optional[str] = Field(
        default=None,
        description="'success', 'failure', 'blocked', etc."
    )

    # ─── Volume / Size ─────────────────────────────────────
    bytes_transferred: Optional[int] = None
    file_count: Optional[int] = None

    # ─── Location ──────────────────────────────────────────
    location: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    is_remote: Optional[bool] = None

    # ─── Risk Indicators ───────────────────────────────────
    risk_indicators: list[str] = Field(
        default_factory=list,
        description="Flags applied during enrichment, e.g. ['after_hours', 'usb_detected']"
    )
    risk_score: Optional[float] = None
    risk_level: Optional[RiskLevel] = None

    # ─── Raw / Extra ───────────────────────────────────────
    raw_payload: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original unmodified event data from the source"
    )
    enrichments: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional enrichment data applied during processing"
    )
    tags: list[str] = Field(default_factory=list)

    model_config = {"use_enum_values": True}

    # ─── Helpers ───────────────────────────────────────────

    def idempotency_key(self) -> str:
        """
        Stable, source-derived idempotency key. Used by ingest endpoints
        to dedupe retried agent submissions.

        Format: '<source_dataset>:<raw_event_id>'.
        """
        if self.raw_event_id:
            return f"{self.source_dataset}:{self.raw_event_id}"
        return f"{self.source_dataset}:{self.event_id}"
