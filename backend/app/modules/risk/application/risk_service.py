"""
ITBIS — Risk Module: daily scoring for a window of days

For every person and every day in the window: collect their signals over the
lookback period, score the day, and store it. Days are scored in order so each
day's trend compares with the scores just before it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.modules.detection.domain.finding import day_start
from app.modules.risk.application.scoring import RiskSettings, score_employee
from app.modules.risk.domain.model import EmployeeRiskScore, RiskSignal


class SignalSource(Protocol):
    async def signals_for(
        self, user_id: str, start: datetime, end: datetime
    ) -> list[RiskSignal]: ...


class RiskScoreStore(Protocol):
    async def upsert_many(self, scores: list[EmployeeRiskScore]) -> None: ...

    async def previous_scores(
        self, user_id: str, before: datetime, days: int = 7
    ) -> list[float]: ...


class RiskService:
    def __init__(
        self,
        signals: SignalSource,
        store: RiskScoreStore,
        settings: RiskSettings | None = None,
    ) -> None:
        self._signals = signals
        self._store = store
        self._settings = settings or RiskSettings()

    async def score_window(
        self, start: datetime, end: datetime, user_ids: list[str]
    ) -> list[EmployeeRiskScore]:
        start = day_start(start)
        days = []
        day = start
        while day < end:
            days.append(day)
            day += timedelta(days=1)

        lookback = max(self._settings.lookback_days, self._settings.historical_lookback_days)
        results: list[EmployeeRiskScore] = []
        for user_id in user_ids:
            signals = await self._signals.signals_for(
                user_id, start - timedelta(days=lookback), end
            )
            previous = await self._store.previous_scores(user_id, start)
            for day in days:
                scored = score_employee(
                    user_id, day, signals, previous_scores=previous, settings=self._settings
                )
                previous.append(scored.score)
                results.append(scored)
        await self._store.upsert_many(results)
        return results
