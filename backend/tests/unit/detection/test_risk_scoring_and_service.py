"""
ITBIS — Unit tests: weighted insider risk scoring and the live detection service.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.anomaly.domain.enums import RiskLevel
from app.modules.detection.application.detection_service import DetectionService
from app.modules.detection.domain.categories import AnomalyCategory
from app.modules.detection.domain.finding import Finding
from app.modules.risk.application.scoring import (
    RiskSettings,
    combine,
    decayed,
    score_employee,
    signals_from_findings,
)
from app.modules.risk.domain.model import RISK_WEIGHTS, RiskComponent, RiskSignal

DAY = datetime(2010, 10, 29, tzinfo=UTC)


def _signal(component: RiskComponent, severity: float, days_ago: int = 0, label: str = "x"):
    return RiskSignal(
        day=DAY - timedelta(days=days_ago), component=component, severity=severity, label=label
    )


# ─── Model ──────────────────────────────────────────────────


def test_weights_follow_the_specification():
    assert RISK_WEIGHTS == {
        RiskComponent.BEHAVIORAL_ANOMALIES: 0.35,
        RiskComponent.PRIVILEGE_MISUSE: 0.25,
        RiskComponent.DATA_ACCESS_VIOLATIONS: 0.20,
        RiskComponent.ACCESS_PATTERN_DEVIATIONS: 0.10,
        RiskComponent.HISTORICAL_SECURITY_EVENTS: 0.10,
    }
    assert sum(RISK_WEIGHTS.values()) == pytest.approx(1.0)


def test_combining_signals_is_bounded_and_monotonic():
    assert combine([]) == 0.0
    assert combine([80]) == pytest.approx(80.0)
    assert combine([50, 50]) == pytest.approx(75.0)
    assert combine([100, 30]) == 100.0
    assert decayed(80, 7, 7) == pytest.approx(40.0)


# ─── Scoring ────────────────────────────────────────────────


def test_every_component_at_its_maximum_is_critical():
    signals = [_signal(c, 100) for c in RiskComponent]
    result = score_employee("jane", DAY, signals)
    assert result.score == 100.0 and result.level == RiskLevel.CRITICAL


def test_score_is_the_weighted_sum_of_components():
    result = score_employee(
        "jane",
        DAY,
        [
            _signal(RiskComponent.BEHAVIORAL_ANOMALIES, 80),
            _signal(RiskComponent.DATA_ACCESS_VIOLATIONS, 80),
            _signal(RiskComponent.ACCESS_PATTERN_DEVIATIONS, 60),
        ],
    )
    assert result.components[RiskComponent.BEHAVIORAL_ANOMALIES] == 80.0
    assert result.score == pytest.approx(0.35 * 80 + 0.20 * 80 + 0.10 * 60)  # 50.0
    assert result.level == RiskLevel.MEDIUM
    assert result.dominant_component == RiskComponent.BEHAVIORAL_ANOMALIES


def test_old_signals_fade_and_future_ones_are_ignored():
    fresh = score_employee("jane", DAY, [_signal(RiskComponent.PRIVILEGE_MISUSE, 80)])
    week_old = score_employee("jane", DAY, [_signal(RiskComponent.PRIVILEGE_MISUSE, 80, 7)])
    too_old = score_employee("jane", DAY, [_signal(RiskComponent.PRIVILEGE_MISUSE, 80, 45)])
    future = score_employee("jane", DAY, [_signal(RiskComponent.PRIVILEGE_MISUSE, 80, -1)])

    assert fresh.components[RiskComponent.PRIVILEGE_MISUSE] == 80.0
    assert week_old.components[RiskComponent.PRIVILEGE_MISUSE] == 40.0
    assert too_old.score == 0.0 and future.score == 0.0


def test_past_incidents_fade_slowly():
    result = score_employee(
        "jane", DAY, [_signal(RiskComponent.HISTORICAL_SECURITY_EVENTS, 80, 90)]
    )
    assert result.components[RiskComponent.HISTORICAL_SECURITY_EVENTS] == 40.0


def test_one_critical_signal_is_prioritised_above_its_weighted_score():
    result = score_employee("jane", DAY, [_signal(RiskComponent.PRIVILEGE_MISUSE, 90)])
    assert result.score == 22.5 and result.level == RiskLevel.LOW
    assert result.priority == 72.0


def test_trend_compares_with_the_previous_week():
    result = score_employee(
        "jane",
        DAY,
        [_signal(RiskComponent.BEHAVIORAL_ANOMALIES, 100)],
        previous_scores=[0, 0, 0, 0, 0, 7, 7, 7],
    )
    assert result.trend == pytest.approx(35.0 - 3.0)
    assert score_employee("jane", DAY, []).trend is None


def test_findings_become_signals_in_their_component():
    finding = Finding(
        user_id="jane",
        day=DAY,
        category=AnomalyCategory.SUSPICIOUS_DEVICE_USAGE,
        detector="suspicious_device_usage",
        severity=55,
        title="Suspicious device usage",
        description="d",
    )
    [signal] = signals_from_findings([finding])
    assert signal.component == RiskComponent.DATA_ACCESS_VIOLATIONS
    result = score_employee("jane", DAY, [signal], settings=RiskSettings(top_signals=1))
    assert result.top_signals[0]["reference"] == finding.key
    assert result.top_signals[0]["component_label"] == "Data access violations"


# ─── Live detection service ─────────────────────────────────


class FakeEvents:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    async def find_events(
        self, *, user_id=None, source_dataset=None, start=None, end=None, limit=100_000
    ):
        self.calls.append((user_id, start, end))
        return [
            d
            for d in self.docs
            if d["user_id"] == user_id and start <= datetime.fromisoformat(d["timestamp"]) < end
        ]


class FakeFindings:
    def __init__(self):
        self.replaced = []

    async def replace_for_user_days(self, user_id, start, end, findings):
        self.replaced.append((user_id, start, end, findings))


def _doc(user, when: datetime, event_type: str, **extra):
    return {"user_id": user, "timestamp": when.isoformat(), "event_type": event_type, **extra}


@pytest.mark.asyncio
async def test_window_days_are_judged_against_prior_history():
    window_start = datetime(2010, 10, 20, tzinfo=UTC)
    docs = []
    for offset in range(1, 31):  # a month of ordinary 09:00 logons before the window
        day = window_start - timedelta(days=offset)
        docs.append(_doc("jane", day.replace(hour=9), "logon", device_id="PC-1"))
    docs.append(_doc("jane", window_start.replace(hour=2), "logon", device_id="PC-1"))
    events, store = FakeEvents(docs), FakeFindings()

    found = await DetectionService(events, store, history_days=45).detect_window(
        window_start, window_start + timedelta(days=1), ["jane"]
    )

    assert [f.category for f in found] == [AnomalyCategory.UNUSUAL_LOGIN_TIME]
    [(user, start, end, stored)] = store.replaced
    assert (user, start, end) == ("jane", window_start, window_start + timedelta(days=1))
    assert stored == found
    assert events.calls[0][1] == window_start - timedelta(days=45)


@pytest.mark.asyncio
async def test_history_findings_outside_the_window_are_not_stored():
    window_start = datetime(2010, 10, 20, tzinfo=UTC)
    burst = [
        _doc("jane", (window_start - timedelta(days=3)).replace(hour=9, minute=m), "logon_failed")
        for m in range(8)
    ]
    store = FakeFindings()
    found = await DetectionService(FakeEvents(burst), store).detect_window(
        window_start, window_start + timedelta(days=1), ["jane"]
    )
    assert found == [] and store.replaced[0][3] == []
