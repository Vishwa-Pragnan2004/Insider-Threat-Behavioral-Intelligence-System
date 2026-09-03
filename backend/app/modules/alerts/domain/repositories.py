"""
ITBIS — Alerts Module: Repository Interfaces
"""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.modules.alerts.domain.entities import Alert
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus


class IUserDirectory(ABC):
    """
    Read-only port for validating that a user exists.

    The alerts module only needs to ask "does this user exist?"
    before persisting an `assigned_to` reference.  We define a
    module-local port (consistent with the existing
    `IAlertRepository` pattern) and inject a concrete implementation
    via FastAPI dependencies.  This keeps the alerts application
    layer free of SQLAlchemy details.
    """

    @abstractmethod
    async def user_exists(self, user_id: str) -> bool:
        """Return True if a user with the given id exists."""
        raise NotImplementedError


class IAlertLinker(ABC):
    """
    Port for the *alert side* of an alert ↔ investigation link.

    The investigations module owns the link/unlink orchestration
    (it is the one that knows an investigation id and an alert id).
    To keep the alert side in sync without coupling the investigations
    application to the concrete AlertService class, this port exposes
    the minimum surface the investigations service needs:

        - link_investigation: set alert.investigation_id
        - unlink_investigation: clear alert.investigation_id

    Both operations are idempotent and must never raise on a
    "no-op" case (e.g. re-linking, or unlinking an unlinked alert).
    Concrete implementations live in the alerts module's application
    layer (AlertService already provides the expected methods).
    """

    @abstractmethod
    async def link_investigation(
        self, alert_id: uuid.UUID, investigation_id: uuid.UUID
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def unlink_investigation(self, alert_id: uuid.UUID) -> None:
        raise NotImplementedError


class IAlertRepository(ABC):
    """Persistence for Alert (MongoDB)."""

    @abstractmethod
    async def upsert(self, alert: Alert) -> tuple[Alert, bool]:
        """
        Insert or fetch an alert by `idempotency_key`.

        Returns (alert, created) where `created` is True iff a new
        document was inserted.  If an alert with the same
        idempotency_key already exists, the existing document is
        returned and `created` is False.  This is the single, atomic
        dedup primitive — callers MUST go through it (not
        `create_or_update`).
        """

    @abstractmethod
    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        """Return a single alert by its UUID, or None if not found."""

    @abstractmethod
    async def list_alerts(
        self,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        user_id: str | None = None,
        assigned_to: str | None = None,
        risk_level: str | None = None,
        source_dataset: str | None = None,
        investigation_id: uuid.UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Alert]:
        """List alerts with optional filters and pagination."""

    @abstractmethod
    async def count_alerts(
        self,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        user_id: str | None = None,
        assigned_to: str | None = None,
        risk_level: str | None = None,
        source_dataset: str | None = None,
        investigation_id: uuid.UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        """Count alerts matching the same filters as `list_alerts`."""

    @abstractmethod
    async def update(self, alert: Alert) -> Alert:
        """Persist a status/assignment/investigation change."""
