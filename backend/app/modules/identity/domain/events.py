"""
ITBIS — Identity Module: Domain Events
Events emitted by the identity module for audit logging and future UEBA integration.

SECURITY: Events must NEVER contain passwords, tokens, or secrets.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.modules.identity.domain.enums import RoleName


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AuthAuditEvent:
    """Base class for all authentication audit events."""

    event_type: str
    occurred_at: datetime = field(default_factory=_now)
    user_id: Optional[uuid.UUID] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool = True
    failure_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class UserRegisteredEvent(AuthAuditEvent):
    """Emitted when a new user successfully registers."""

    event_type: str = "USER_REGISTERED"
    email: Optional[str] = None
    assigned_role: Optional[RoleName] = None


@dataclass(frozen=True)
class LoginSuccessEvent(AuthAuditEvent):
    """Emitted on successful authentication."""

    event_type: str = "LOGIN_SUCCESS"


@dataclass(frozen=True)
class LoginFailureEvent(AuthAuditEvent):
    """Emitted on failed authentication attempt."""

    event_type: str = "LOGIN_FAILURE"
    success: bool = False


@dataclass(frozen=True)
class LogoutEvent(AuthAuditEvent):
    """Emitted when a user explicitly logs out."""

    event_type: str = "LOGOUT"


@dataclass(frozen=True)
class TokenRefreshEvent(AuthAuditEvent):
    """Emitted when a refresh token is used to obtain a new access token."""

    event_type: str = "TOKEN_REFRESH"


@dataclass(frozen=True)
class TokenRevokedEvent(AuthAuditEvent):
    """Emitted when a token is explicitly revoked."""

    event_type: str = "TOKEN_REVOKED"


@dataclass(frozen=True)
class PasswordChangedEvent(AuthAuditEvent):
    """Emitted when a user successfully changes their password."""

    event_type: str = "PASSWORD_CHANGED"


@dataclass(frozen=True)
class AccountDisabledEvent(AuthAuditEvent):
    """Emitted when an account is disabled by an administrator."""

    event_type: str = "ACCOUNT_DISABLED"
    disabled_by: Optional[uuid.UUID] = None
