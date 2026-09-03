"""
ITBIS — Alerts Module: Alert Service (lifecycle, assignment, listing)

Higher-level operations on alerts after they've been created —
acknowledge, change status, assign, link/unlink investigations.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from app.modules.alerts.domain.entities import Alert, allowed_next_statuses
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.exceptions import (
    AlertNotFoundError,
    AssigneeNotFoundError,
    IllegalAlertStatusTransitionError,
)
from app.modules.alerts.domain.repositories import (
    IAlertLinker,
    IAlertRepository,
    IUserDirectory,
)

log = structlog.get_logger(__name__)


class AlertService(IAlertLinker):
    """
    Lifecycle and workflow operations on alerts.

    Implements ``IAlertLinker`` so that the investigations module can
    request two-sided link/unlink updates through the abstract port
    without depending on the concrete class.
    """

    def __init__(
        self,
        alert_repo: IAlertRepository,
        user_directory: IUserDirectory,
    ) -> None:
        self.alert_repo = alert_repo
        self.user_directory = user_directory

    # ─── Lookups ─────────────────────────────────────────

    async def get(self, alert_id: uuid.UUID) -> Alert:
        a = await self.alert_repo.get_by_id(alert_id)
        if a is None:
            raise AlertNotFoundError(f"Alert {alert_id} not found")
        return a

    async def list(
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
    ) -> tuple[list[Alert], int]:
        items = await self.alert_repo.list_alerts(
            status=status,
            severity=severity,
            user_id=user_id,
            assigned_to=assigned_to,
            risk_level=risk_level,
            source_dataset=source_dataset,
            investigation_id=investigation_id,
            start=start,
            end=end,
            skip=skip,
            limit=limit,
        )
        total = await self.alert_repo.count_alerts(
            status=status,
            severity=severity,
            user_id=user_id,
            assigned_to=assigned_to,
            risk_level=risk_level,
            source_dataset=source_dataset,
            investigation_id=investigation_id,
            start=start,
            end=end,
        )
        return items, total

    # ─── Workflow ────────────────────────────────────────

    async def acknowledge(self, alert_id: uuid.UUID) -> Alert:
        return await self._change_status(alert_id, AlertStatus.ACKNOWLEDGED)

    async def change_status(
        self, alert_id: uuid.UUID, new_status: AlertStatus
    ) -> Alert:
        return await self._change_status(alert_id, new_status)

    async def assign(self, alert_id: uuid.UUID, user_id: str) -> Alert:
        # Validate the assignee exists before persisting the change.
        if not await self.user_directory.user_exists(user_id):
            raise AssigneeNotFoundError(
                f"User {user_id!r} does not exist; cannot assign alert"
            )
        a = await self.get(alert_id)
        a.assign(user_id)
        saved = await self.alert_repo.update(a)
        log.info(
            "alerts.assigned",
            alert_id=str(alert_id),
            assigned_to=user_id,
        )
        return saved

    async def link_investigation(
        self,
        alert_id: uuid.UUID,
        investigation_id: uuid.UUID,
    ) -> Alert:
        """
        Update the alert side of the link only.

        The two-sided invariant is enforced at the **service
        composition root**: when the router wires the link, the
        investigation service is the one that calls both this
        method (alert side) and its own persistence (investigation
        side).  This method is intentionally minimal so the alert
        module does not need to know about the investigation service.

        Idempotent: re-linking the same pair is a no-op.
        """
        a = await self.get(alert_id)
        if a.investigation_id == investigation_id:
            return a
        a.link_investigation(investigation_id)
        saved_alert = await self.alert_repo.update(a)
        log.info(
            "alerts.linked_to_investigation",
            alert_id=str(alert_id),
            investigation_id=str(investigation_id),
        )
        return saved_alert

    async def unlink_investigation(self, alert_id: uuid.UUID) -> Alert:
        """
        Update the alert side of the unlink only.

        The two-sided invariant is enforced at the **service
        composition root**: the investigation service is the one
        that calls both this method (alert side) and its own
        persistence (investigation side).

        Idempotent: unlinking an already-unlinked alert is a no-op.
        """
        a = await self.get(alert_id)
        if a.investigation_id is None:
            return a
        a.unlink_investigation()
        saved_alert = await self.alert_repo.update(a)
        log.info(
            "alerts.unlinked_from_investigation",
            alert_id=str(alert_id),
        )
        return saved_alert

    # ─── Internals ──────────────────────────────────────

    async def _change_status(
        self, alert_id: uuid.UUID, new_status: AlertStatus
    ) -> Alert:
        a = await self.get(alert_id)
        # Entity-level validation.  The entity itself raises ValueError
        # for illegal transitions; we translate to a domain exception.
        if new_status == a.status:
            # Idempotent no-op (the entity's `change_status` silently
            # ignores self-loops, but we still want to update nothing).
            return a
        if new_status not in allowed_next_statuses(a.status):
            raise IllegalAlertStatusTransitionError(
                f"Cannot transition alert {alert_id} from "
                f"{a.status.value} to {new_status.value}"
            )
        a.change_status(new_status)
        saved = await self.alert_repo.update(a)
        log.info(
            "alerts.status_changed",
            alert_id=str(alert_id),
            new_status=new_status.value,
        )
        return saved
