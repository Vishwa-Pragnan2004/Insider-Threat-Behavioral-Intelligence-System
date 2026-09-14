"""
ITBIS — Users Module: access requests (domain)

A person who needs ITBIS asks for an account and the role they need. The
account exists from the moment they ask, but stays disabled, with no roles,
until an administrator approves the request (choosing the roles actually
granted) or rejects it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from app.modules.identity.domain.enums import RoleName

#: Administrator access is never self-service: an existing admin grants it.
REQUESTABLE_ROLES = frozenset(role for role in RoleName if role != RoleName.ADMIN)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AccessRequestStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class AccessRequest:
    user_id: uuid.UUID
    requested_role: RoleName
    reason: str
    status: AccessRequestStatus = AccessRequestStatus.PENDING
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    decided_at: datetime | None = None
    decided_by: uuid.UUID | None = None
    decision_note: str | None = None
    granted_roles: list[RoleName] = field(default_factory=list)

    @property
    def is_pending(self) -> bool:
        return self.status == AccessRequestStatus.PENDING

    def approve(self, actor_id: uuid.UUID, roles: list[RoleName]) -> None:
        self._decide(AccessRequestStatus.APPROVED, actor_id)
        self.granted_roles = list(roles)

    def reject(self, actor_id: uuid.UUID, note: str | None) -> None:
        self._decide(AccessRequestStatus.REJECTED, actor_id)
        self.decision_note = note

    def _decide(self, status: AccessRequestStatus, actor_id: uuid.UUID) -> None:
        self.status = status
        self.decided_by = actor_id
        self.decided_at = _utcnow()


@dataclass(frozen=True)
class AccessRequestView:
    """A request together with who asked and who decided, for the admin queue."""

    request: AccessRequest
    username: str
    email: str
    full_name: str
    decided_by_username: str | None = None
