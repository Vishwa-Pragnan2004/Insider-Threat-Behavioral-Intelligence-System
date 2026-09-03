"""
ITBIS — Investigations Module: Domain Entities
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.modules.investigations.domain.enums import InvestigationStatus


def _utcnow() -> datetime:
    from datetime import UTC
    return datetime.now(UTC)


# ─── InvestigationNote (immutable) ─────────────────────────


@dataclass(frozen=True)
class InvestigationNote:
    """
    Append-only timeline note.  Notes are IMMUTABLE — the only
    mutation is the entity's own __init__ (frozen=True) and there is
    no API endpoint to edit or delete them.
    """

    investigation_id: uuid.UUID
    author_id: str
    content: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)


# ─── Investigation ────────────────────────────────────────


@dataclass
class Investigation:
    """
    A security case that groups one or more alerts and tracks the
    analyst's workflow from creation to closure.
    """

    title: str
    description: str
    severity: str
    created_by: str
    related_alert_ids: list[uuid.UUID] = field(default_factory=list)
    related_user_ids: list[str] = field(default_factory=list)
    resolution: str | None = None
    assigned_to: str | None = None
    status: InvestigationStatus = InvestigationStatus.OPEN
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    closed_at: datetime | None = None

    # ─── Behaviour ────────────────────────────────────
    def change_status(self, target: InvestigationStatus) -> None:
        """Apply a lifecycle status change, validating the transition."""
        from app.modules.investigations.domain.enums import is_valid_transition

        if target == self.status:
            return  # idempotent no-op
        if not is_valid_transition(self.status, target):
            raise ValueError(
                f"Illegal investigation status transition: "
                f"{self.status.value} -> {target.value}"
            )
        self.status = target
        self.updated_at = _utcnow()
        if target == InvestigationStatus.CLOSED:
            self.closed_at = self.updated_at

    def assign(self, user_id: str) -> None:
        self.assigned_to = user_id
        self.updated_at = _utcnow()

    def add_alert(self, alert_id: uuid.UUID, user_id: str | None) -> None:
        if alert_id not in self.related_alert_ids:
            self.related_alert_ids.append(alert_id)
        if user_id and user_id not in self.related_user_ids:
            self.related_user_ids.append(user_id)
        self.updated_at = _utcnow()

    def remove_alert(self, alert_id: uuid.UUID) -> None:
        if alert_id in self.related_alert_ids:
            self.related_alert_ids.remove(alert_id)
        self.updated_at = _utcnow()

    def set_resolution(self, text: str | None) -> None:
        self.resolution = text
        self.updated_at = _utcnow()
