"""
ITBIS — Unit tests: daily risk scoring over a window and insider-risk alerts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.alerts.application.risk_alert_service import RiskAlertService, risk_alert_key
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.detection.domain.categories import AnomalyCategory
from app.modules.detection.domain.finding import Finding
from app.modules.risk.application.risk_service import RiskService
from app.modules.risk.application.scoring import score_employee, signals_from_findings
from app.modules.risk.domain.model import RiskComponent, RiskSignal

DAY = datetime(2010, 10, 29, tzinfo=UTC)


def _finding(category: AnomalyCategory, severity: float, day: datetime = DAY, user="jane"):
    return Finding(
        user_id=user,
        day=day,
        category=category,
        detector=category.value.lower(),
        severity=severity,
        title=category.value.title(),
        description="because",
    )


class FakeSignals:
    def __init__(self, signals):
        self.signals = signals
        self.calls = []

    async def signals_for(self, user_id, start, end):
        self.calls.append((user_id, start, end))
        return self.signals


class FakeScores:
    def __init__(self, previous=None):
        self.previous = previous or []
        self.saved = []

    async def upsert_many(self, scores):
        self.saved.extend(scores)

    async def previous_scores(self, user_id, before, days=7):
        return list(self.previous)


class FakeAlerts:
    def __init__(self):
        self.by_key = {}
        self.content_updates = 0

    async def upsert(self, alert):
        if alert.idempotency_key in self.by_key:
            return self.by_key[alert.idempotency_key], False
        self.by_key[alert.idempotency_key] = alert
        return alert, True

    async def update_content(self, alert):
        self.content_updates += 1
        return alert


# ─── Risk service ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_each_day_in_the_window_is_scored_in_order():
    leak = _finding(AnomalyCategory.ABNORMAL_DATA_DOWNLOAD, 80, DAY)
    signals = FakeSignals(signals_from_findings([leak]))
    store = FakeScores(previous=[0.0] * 7)

    scores = await RiskService(signals, store).score_window(DAY, DAY + timedelta(days=3), ["jane"])

    assert [s.day for s in scores] == [DAY + timedelta(days=i) for i in range(3)]
    assert [s.components[RiskComponent.DATA_ACCESS_VIOLATIONS] for s in scores] == [
        80.0,
        72.5,
        65.6,
    ]
    assert scores[0].trend == 16.0 and scores[1].trend == pytest.approx(14.5 - 16.0 / 7, abs=0.1)
    assert store.saved == scores
    assert signals.calls[0][1] == DAY - timedelta(days=365)


# ─── Alerts ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_high_priority_day_raises_one_explained_alert():
    findings = [
        _finding(AnomalyCategory.ABNORMAL_DATA_DOWNLOAD, 80),
        _finding(AnomalyCategory.UNUSUAL_LOGIN_TIME, 65),
    ]
    score = score_employee("jane", DAY, signals_from_findings(findings))
    alerts = FakeAlerts()

    alert, created = await RiskAlertService(alerts).raise_for(score, findings)

    assert created and alert.source == "insider_risk"
    assert alert.idempotency_key == risk_alert_key("jane", "2010-10-29")
    assert alert.anomaly_result_id is None
    assert alert.categories == ["ABNORMAL_DATA_DOWNLOAD", "UNUSUAL_LOGIN_TIME"]
    assert alert.severity == AlertSeverity.HIGH and alert.priority == 64.0
    assert alert.title == "High insider risk: Abnormal data download / upload, Unusual login time"
    assert alert.employee_risk_score == score.score
    assert [f.severity for f in alert.findings] == [80.0, 65.0]


@pytest.mark.asyncio
async def test_low_priority_days_raise_nothing():
    findings = [_finding(AnomalyCategory.SUSPICIOUS_DEVICE_USAGE, 55)]
    score = score_employee("jane", DAY, signals_from_findings(findings))
    assert await RiskAlertService(FakeAlerts()).raise_for(score, findings) == (None, False)


@pytest.mark.asyncio
async def test_fading_findings_from_earlier_days_do_not_re_alert():
    yesterday = [_finding(AnomalyCategory.PRIVILEGE_ABUSE, 95, DAY - timedelta(days=1))]
    score = score_employee("jane", DAY, signals_from_findings(yesterday))
    assert score.priority >= 60
    assert await RiskAlertService(FakeAlerts()).raise_for(score, yesterday) == (None, False)


@pytest.mark.asyncio
async def test_a_model_anomaly_today_can_carry_an_alert():
    signal = RiskSignal(
        day=DAY,
        component=RiskComponent.BEHAVIORAL_ANOMALIES,
        severity=90,
        label="model",
        category=AnomalyCategory.BEHAVIORAL_ANOMALY,
    )
    score = score_employee("jane", DAY, [signal])
    alert, created = await RiskAlertService(FakeAlerts()).raise_for(score, [])
    assert created and alert.categories == ["BEHAVIORAL_ANOMALY"]


@pytest.mark.asyncio
async def test_open_alert_is_refreshed_as_evidence_grows_but_not_once_picked_up():
    alerts = FakeAlerts()
    service = RiskAlertService(alerts)
    first = [_finding(AnomalyCategory.ABNORMAL_DATA_DOWNLOAD, 80)]
    await service.raise_for(score_employee("jane", DAY, signals_from_findings(first)), first)

    more = first + [_finding(AnomalyCategory.PRIVILEGE_ABUSE, 95)]
    alert, created = await service.raise_for(
        score_employee("jane", DAY, signals_from_findings(more)), more
    )
    assert not created and alerts.content_updates == 1
    assert alert.priority == 76.0 and len(alert.findings) == 2
    assert alert.severity == AlertSeverity.HIGH

    alert.status = AlertStatus.IN_PROGRESS
    even_more = more + [_finding(AnomalyCategory.UNUSUAL_LOGIN_TIME, 70)]
    await service.raise_for(
        score_employee("jane", DAY, signals_from_findings(even_more)), even_more
    )
    assert alerts.content_updates == 1, "an analyst's alert is left as they found it"
