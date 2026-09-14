"""
ITBIS — Detection Module: live detection

Runs the category detectors over a window of days for a set of people. For
each person it replays their recent history (`history_days` before the window)
through a `UserTimeline`, so every day in the window is judged against what
came before it, then stores that window's findings.

Replaying history each run keeps the live pipeline stateless: there is no
stored profile to drift out of step with the events, and results match a
full dataset replay of the same days.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import structlog

from app.modules.detection.application.activity import EventView
from app.modules.detection.application.detectors import DetectionContext, UserTimeline
from app.modules.detection.domain.finding import Finding, day_start

log = structlog.get_logger(__name__)


class EventSource(Protocol):
    async def find_events(
        self,
        *,
        user_id: str | None = None,
        source_dataset: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100_000,
    ) -> list[dict]: ...


class FindingStore(Protocol):
    async def replace_for_user_days(
        self, user_id: str, start: datetime, end: datetime, findings: list[Finding]
    ) -> None: ...


def events_by_day(docs: list[dict]) -> dict[date, list[EventView]]:
    days: dict[date, list[EventView]] = defaultdict(list)
    for doc in docs:
        view = EventView.from_doc(doc)
        if view is not None:
            days[view.timestamp.date()].append(view)
    return days


class DetectionService:
    def __init__(
        self,
        event_source: EventSource,
        finding_store: FindingStore,
        *,
        history_days: int = 60,
        context_provider: Callable[[], DetectionContext] | None = None,
        history_limit: int = 500_000,
    ) -> None:
        self._events = event_source
        self._findings = finding_store
        self._history_days = history_days
        self._context_provider = context_provider or DetectionContext
        self._history_limit = history_limit

    async def detect_window(
        self, start: datetime, end: datetime, user_ids: list[str]
    ) -> list[Finding]:
        start, end = (
            day_start(start),
            day_start(end - timedelta(microseconds=1)) + timedelta(days=1),
        )
        context = self._context_provider()
        found: list[Finding] = []
        for user_id in user_ids:
            try:
                user_findings = await self.detect_user(user_id, start, end, context)
            except Exception:  # noqa: BLE001 - one person's bad data must not stop the run
                log.exception("detection.user_failed", user_id=user_id)
                continue
            found.extend(user_findings)
        return found

    async def detect_user(
        self, user_id: str, start: datetime, end: datetime, context: DetectionContext
    ) -> list[Finding]:
        docs = await self._events.find_events(
            user_id=user_id,
            start=start - timedelta(days=self._history_days),
            end=end,
            limit=self._history_limit,
        )
        timeline = UserTimeline(user_id, context)
        window_findings: list[Finding] = []
        for day, events in sorted(events_by_day(docs).items()):
            _, findings = timeline.process_day(day, events)
            if datetime(day.year, day.month, day.day, tzinfo=UTC) >= start:
                window_findings.extend(findings)
        await self._findings.replace_for_user_days(user_id, start, end, window_findings)
        return window_findings
