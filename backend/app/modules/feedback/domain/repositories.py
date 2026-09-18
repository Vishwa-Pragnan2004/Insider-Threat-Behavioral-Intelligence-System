"""
ITBIS — Feedback Module: Repository ports
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import date

from app.modules.feedback.domain.entities import AnalystVerdict


class IVerdictRepository(ABC):
    @abstractmethod
    async def add(self, verdict: AnalystVerdict) -> AnalystVerdict:
        """Persist a new verdict."""

    @abstractmethod
    async def update(self, verdict: AnalystVerdict) -> AnalystVerdict:
        """Persist changes to an existing verdict (only supersession)."""

    @abstractmethod
    async def current_for_alert(self, alert_id: uuid.UUID) -> AnalystVerdict | None:
        """The verdict in force for an alert, or None if never judged."""

    @abstractmethod
    async def history_for_alert(self, alert_id: uuid.UUID) -> list[AnalystVerdict]:
        """Every verdict ever recorded for an alert, oldest first."""

    @abstractmethod
    async def current_for_alerts(
        self, alert_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AnalystVerdict]:
        """Current verdicts for many alerts at once (list views)."""

    @abstractmethod
    async def list_current(
        self,
        *,
        since: date | None = None,
        until: date | None = None,
        subject_user_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AnalystVerdict], int]:
        """Current verdicts and the total count, newest first."""
