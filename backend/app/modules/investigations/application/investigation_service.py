"""
ITBIS — Investigations Module: Investigation Service

Workflow operations on investigations: creation, alert linking,
status transitions, assignment, and (immutable) notes.
"""
from __future__ import annotations

import uuid

import structlog

from app.modules.alerts.domain.repositories import IAlertLinker
from app.modules.investigations.domain.entities import (
    Investigation,
    InvestigationNote,
)
from app.modules.investigations.domain.enums import InvestigationStatus
from app.modules.investigations.domain.exceptions import (
    AssigneeNotFoundError,
    IllegalInvestigationStatusTransitionError,
    InvestigationNotFoundError,
)
from app.modules.investigations.domain.repositories import (
    IInvestigationNoteRepository,
    IInvestigationRepository,
    IUserDirectory,
)

log = structlog.get_logger(__name__)


class InvestigationService:
    """All workflow operations on investigations + notes."""

    def __init__(
        self,
        investigation_repo: IInvestigationRepository,
        note_repo: IInvestigationNoteRepository,
        user_directory: IUserDirectory,
    ) -> None:
        self.investigation_repo = investigation_repo
        self.note_repo = note_repo
        self.user_directory = user_directory

    # ─── Lookups ─────────────────────────────────────────

    async def get(self, investigation_id: uuid.UUID) -> Investigation:
        inv = await self.investigation_repo.get_by_id(investigation_id)
        if inv is None:
            raise InvestigationNotFoundError(
                f"Investigation {investigation_id} not found"
            )
        return inv

    async def list(
        self,
        *,
        status: InvestigationStatus | None = None,
        assigned_to: str | None = None,
        severity: str | None = None,
        related_user_id: str | None = None,
        created_by: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Investigation], int]:
        items = await self.investigation_repo.list_investigations(
            status=status,
            assigned_to=assigned_to,
            severity=severity,
            related_user_id=related_user_id,
            created_by=created_by,
            skip=skip,
            limit=limit,
        )
        total = await self.investigation_repo.count_investigations(
            status=status,
            assigned_to=assigned_to,
            severity=severity,
            related_user_id=related_user_id,
            created_by=created_by,
        )
        return items, total

    # ─── Creation ────────────────────────────────────────

    async def create(
        self,
        *,
        title: str,
        description: str,
        severity: str,
        created_by: str,
        related_alert_ids: list[uuid.UUID],
        related_user_ids: list[str],
        assigned_to: str | None = None,
    ) -> Investigation:
        inv = Investigation(
            title=title,
            description=description,
            severity=severity,
            created_by=created_by,
            related_alert_ids=list(related_alert_ids),
            related_user_ids=list(related_user_ids),
            assigned_to=assigned_to,
        )
        saved = await self.investigation_repo.upsert(inv)
        log.info(
            "investigations.created",
            investigation_id=str(saved.id),
            created_by=created_by,
            alerts=len(related_alert_ids),
        )
        return saved

    # ─── Workflow ────────────────────────────────────────

    async def change_status(
        self,
        investigation_id: uuid.UUID,
        new_status: InvestigationStatus,
        *,
        resolution: str | None = None,
    ) -> Investigation:
        inv = await self.get(investigation_id)
        if new_status == inv.status:
            return inv  # idempotent no-op
        # The entity raises ValueError on illegal transition; translate.
        try:
            inv.change_status(new_status)
        except ValueError as exc:
            raise IllegalInvestigationStatusTransitionError(str(exc)) from exc
        if resolution is not None:
            inv.set_resolution(resolution)
        saved = await self.investigation_repo.upsert(inv)
        log.info(
            "investigations.status_changed",
            investigation_id=str(saved.id),
            new_status=new_status.value,
        )
        return saved

    async def assign(
        self, investigation_id: uuid.UUID, user_id: str
    ) -> Investigation:
        # Validate the assignee exists before persisting the change.
        if not await self.user_directory.user_exists(user_id):
            raise AssigneeNotFoundError(
                f"User {user_id!r} does not exist; cannot assign investigation"
            )
        inv = await self.get(investigation_id)
        inv.assign(user_id)
        saved = await self.investigation_repo.upsert(inv)
        log.info(
            "investigations.assigned",
            investigation_id=str(saved.id),
            assigned_to=user_id,
        )
        return saved

    async def add_alert(
        self,
        investigation_id: uuid.UUID,
        alert_id: uuid.UUID,
        user_id: str | None,
        alert_service: IAlertLinker | None = None,
    ) -> Investigation:
        """
        Link an alert to an investigation.

        Maintains the two-sided invariant: the investigation's
        `related_alert_ids` is updated AND, if an `alert_service` is
        provided, the alert's `investigation_id` is also updated
        (no-op if already set).  Idempotent: re-linking the same pair
        is a no-op.
        """
        inv = await self.get(investigation_id)
        if alert_id in inv.related_alert_ids:
            # Idempotent: already linked.
            return inv
        inv.add_alert(alert_id, user_id)
        saved = await self.investigation_repo.upsert(inv)
        if alert_service is not None:
            try:
                # Update the alert side.  AlertService.link_investigation
                # handles its own idempotency and exception swallowing
                # (logs internally, re-raises) — we re-raise to make
                # the failure auditable.
                await alert_service.link_investigation(
                    alert_id=alert_id,
                    investigation_id=investigation_id,
                )
            except Exception:
                log.exception(
                    "investigations.add_alert.alert_side_failed",
                    investigation_id=str(investigation_id),
                    alert_id=str(alert_id),
                )
                raise
        log.info(
            "investigations.alert_linked",
            investigation_id=str(saved.id),
            alert_id=str(alert_id),
        )
        return saved

    async def remove_alert(
        self,
        investigation_id: uuid.UUID,
        alert_id: uuid.UUID,
        alert_service: IAlertLinker | None = None,
    ) -> Investigation:
        """
        Unlink an alert from an investigation.

        Maintains the two-sided invariant: the investigation's
        `related_alert_ids` is updated AND, if an `alert_service` is
        provided, the alert's `investigation_id` is cleared.
        Idempotent.
        """
        inv = await self.get(investigation_id)
        if alert_id not in inv.related_alert_ids:
            # Idempotent: already unlinked.
            return inv
        inv.remove_alert(alert_id)
        saved = await self.investigation_repo.upsert(inv)
        if alert_service is not None:
            try:
                await alert_service.unlink_investigation(alert_id)
            except Exception:
                log.exception(
                    "investigations.remove_alert.alert_side_failed",
                    investigation_id=str(investigation_id),
                    alert_id=str(alert_id),
                )
                raise
        log.info(
            "investigations.alert_unlinked",
            investigation_id=str(saved.id),
            alert_id=str(alert_id),
        )
        return saved

    # ─── Notes (immutable) ────────────────────────────────

    async def add_note(
        self,
        investigation_id: uuid.UUID,
        author_id: str,
        content: str,
    ) -> InvestigationNote:
        # Verify the investigation exists first (don't pollute the notes
        # collection with notes for non-existent investigations).
        await self.get(investigation_id)
        note = InvestigationNote(
            investigation_id=investigation_id,
            author_id=author_id,
            content=content,
        )
        await self.note_repo.append(note)
        log.info(
            "investigations.note_added",
            investigation_id=str(investigation_id),
            note_id=str(note.id),
            author_id=author_id,
        )
        return note

    async def list_notes(
        self, investigation_id: uuid.UUID
    ) -> list[InvestigationNote]:
        await self.get(investigation_id)  # existence check
        return await self.note_repo.list_for_investigation(investigation_id)
