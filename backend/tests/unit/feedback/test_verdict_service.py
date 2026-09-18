"""
ITBIS — Unit tests: recording what an alert turned out to be.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.domain.entities import Alert, AlertFinding
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.exceptions import AlertNotFoundError
from app.modules.feedback.application.verdict_service import (
    EmptyRationaleError,
    VerdictService,
)
from app.modules.feedback.domain.entities import AnalystVerdict
from app.modules.feedback.domain.enums import Verdict

DAY = datetime(2026, 9, 14, tzinfo=UTC)


def _alert(**overrides) -> Alert:
    defaults = dict(
        idempotency_key="jane|daily|2026-09-14|weighted_risk_v1",
        anomaly_result_id=None,
        user_id="jane",
        source_dataset="agent",
        window="daily",
        window_start=DAY,
        window_end=DAY,
        model_version="itbis_behavior_v3",
        feature_version="behavioral_features_v1",
        title="High insider risk",
        description="...",
        risk_score=71.0,
        risk_level="HIGH",
        severity=AlertSeverity.HIGH,
        source="insider_risk",
        categories=["SUSPICIOUS_DEVICE_USAGE", "ABNORMAL_DATA_DOWNLOAD"],
        employee_risk_score=64.2,
        priority=82.5,
        findings=[
            AlertFinding(
                category="SUSPICIOUS_DEVICE_USAGE",
                title="USB used out of hours",
                severity=70.0,
                description="...",
                detector="suspicious_device_usage",
                day=DAY,
            ),
            AlertFinding(
                category="ABNORMAL_DATA_DOWNLOAD",
                title="Copied 400 files",
                severity=60.0,
                description="...",
                detector="abnormal_data_download",
                day=DAY,
            ),
        ],
    )
    return Alert(**{**defaults, **overrides})


class FakeAlertRepo:
    def __init__(self, alert: Alert | None) -> None:
        self.alert = alert
        self.updates = 0

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        if self.alert is not None and self.alert.id == alert_id:
            return self.alert
        return None

    async def update(self, alert: Alert) -> Alert:
        self.updates += 1
        self.alert = alert
        return alert


class FakeUserDirectory:
    async def user_exists(self, user_id: str) -> bool:
        return True


class FakeVerdictRepo:
    """In-memory stand-in that enforces the one-current-verdict rule."""

    def __init__(self) -> None:
        self.rows: list[AnalystVerdict] = []

    async def add(self, verdict: AnalystVerdict) -> AnalystVerdict:
        live = [
            v for v in self.rows if v.alert_id == verdict.alert_id and v.superseded_at is None
        ]
        assert not live, "two current verdicts for one alert"
        self.rows.append(verdict)
        return verdict

    async def update(self, verdict: AnalystVerdict) -> AnalystVerdict:
        return verdict

    async def current_for_alert(self, alert_id: uuid.UUID) -> AnalystVerdict | None:
        return next(
            (v for v in self.rows if v.alert_id == alert_id and v.superseded_at is None), None
        )

    async def history_for_alert(self, alert_id: uuid.UUID) -> list[AnalystVerdict]:
        return sorted(
            (v for v in self.rows if v.alert_id == alert_id), key=lambda v: v.decided_at
        )

    async def current_for_alerts(self, alert_ids):
        return {
            v.alert_id: v
            for v in self.rows
            if v.alert_id in set(alert_ids) and v.superseded_at is None
        }

    async def list_current(
        self, *, since=None, until=None, subject_user_id=None, limit=500, offset=0
    ):
        rows = [v for v in self.rows if v.superseded_at is None]
        if since:
            rows = [v for v in rows if v.subject_day >= since]
        if until:
            rows = [v for v in rows if v.subject_day <= until]
        if subject_user_id:
            rows = [v for v in rows if v.subject_user_id == subject_user_id]
        rows.sort(key=lambda v: v.decided_at, reverse=True)
        return rows[offset : offset + limit], len(rows)


def _service(alert: Alert | None) -> tuple[VerdictService, FakeVerdictRepo, FakeAlertRepo]:
    alert_repo = FakeAlertRepo(alert)
    alerts = AlertService(alert_repo=alert_repo, user_directory=FakeUserDirectory())
    repo = FakeVerdictRepo()
    return VerdictService(repo, alerts), repo, alert_repo


# ─── Recording ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_confirmed_threat_is_recorded_with_the_evidence_behind_it():
    alert = _alert()
    service, _, _ = _service(alert)

    verdict, updated = await service.record(
        alert.id,
        verdict=Verdict.CONFIRMED_THREAT,
        rationale="Confirmed with HR: resigned on the 12th, copied the client list.",
        decided_by="analyst1",
    )

    assert verdict.subject_user_id == "jane" and verdict.subject_day == DAY.date()
    assert verdict.decided_by == "analyst1" and verdict.is_current
    # The label is only meaningful alongside what the system believed.
    assert verdict.evidence.priority == 82.5
    assert verdict.evidence.risk_score == 64.2
    assert verdict.evidence.model_version == "itbis_behavior_v3"
    assert verdict.evidence.detectors == [
        "abnormal_data_download",
        "suspicious_device_usage",
    ]
    # A confirmed threat closes the alert.
    assert updated.status == AlertStatus.RESOLVED


@pytest.mark.asyncio
async def test_benign_closes_the_alert_as_a_false_positive():
    alert = _alert()
    service, _, _ = _service(alert)
    _, updated = await service.record(
        alert.id, verdict=Verdict.BENIGN, rationale="Quarterly backup, approved.",
        decided_by="analyst1",
    )
    assert updated.status == AlertStatus.FALSE_POSITIVE


@pytest.mark.asyncio
async def test_inconclusive_leaves_the_alert_open():
    """'We looked and still don't know' is not a closure."""
    alert = _alert(status=AlertStatus.IN_PROGRESS)
    service, _, _ = _service(alert)
    verdict, updated = await service.record(
        alert.id, verdict=Verdict.INCONCLUSIVE, rationale="Owner on leave until October.",
        decided_by="analyst1",
    )
    assert updated.status == AlertStatus.IN_PROGRESS
    assert verdict.training_label is None


@pytest.mark.asyncio
async def test_a_verdict_is_recorded_even_when_the_alert_cannot_move():
    """Revising a months-old call must not fail on a terminal status."""
    alert = _alert(status=AlertStatus.RESOLVED)
    service, _, _ = _service(alert)

    verdict, updated = await service.record(
        alert.id, verdict=Verdict.BENIGN, rationale="Re-reviewed: the transfer was sanctioned.",
        decided_by="manager1",
    )

    assert verdict.verdict is Verdict.BENIGN
    # The verdict is the record of truth; the queue position stays put.
    assert updated.status == AlertStatus.RESOLVED


@pytest.mark.asyncio
async def test_re_judging_supersedes_the_earlier_verdict_and_keeps_it():
    alert = _alert()
    service, repo, _ = _service(alert)
    await service.record(
        alert.id, verdict=Verdict.BENIGN, rationale="Looked routine.", decided_by="analyst1"
    )
    first = repo.rows[0]
    first.supersede(uuid.uuid4())  # the fake repo's update() is a no-op

    second, _ = await service.record(
        alert.id,
        verdict=Verdict.CONFIRMED_THREAT,
        rationale="HR later confirmed exfiltration.",
        decided_by="analyst2",
    )

    history = await service.history_for_alert(alert.id)
    assert len(history) == 2
    assert history[-1].id == second.id and second.is_current
    assert not history[0].is_current


@pytest.mark.asyncio
async def test_a_verdict_without_an_explanation_is_refused():
    alert = _alert()
    service, repo, _ = _service(alert)
    with pytest.raises(EmptyRationaleError):
        await service.record(
            alert.id, verdict=Verdict.BENIGN, rationale="   ", decided_by="analyst1"
        )
    assert repo.rows == []


@pytest.mark.asyncio
async def test_judging_an_unknown_alert_raises():
    service, _, _ = _service(None)
    with pytest.raises(AlertNotFoundError):
        await service.record(
            uuid.uuid4(), verdict=Verdict.BENIGN, rationale="n/a", decided_by="analyst1"
        )


# ─── Measurement and training data ─────────────────────────


async def _record(service, verdict: Verdict, alert: Alert) -> None:
    await service.record(
        alert.id, verdict=verdict, rationale="because", decided_by="analyst1"
    )


@pytest.mark.asyncio
async def test_precision_counts_only_decisive_calls():
    alerts = [_alert(user_id=f"u{i}") for i in range(4)]
    service, repo, alert_repo = _service(alerts[0])

    for alert, verdict in zip(
        alerts,
        [
            Verdict.CONFIRMED_THREAT,
            Verdict.CONFIRMED_THREAT,
            Verdict.BENIGN,
            Verdict.POLICY_VIOLATION,
        ],
        strict=True,
    ):
        alert_repo.alert = alert
        await _record(service, verdict, alert)

    stats = await service.stats()
    assert stats.total == 4
    # 2 threats out of 3 decisive calls; the policy violation is neither.
    assert stats.precision == pytest.approx(2 / 3, abs=0.001)
    assert stats.threats == 2 and stats.benign == 1
    assert stats.trainable == 3


@pytest.mark.asyncio
async def test_precision_is_none_before_anyone_has_called_one_either_way():
    alert = _alert()
    service, _, _ = _service(alert)
    await _record(service, Verdict.INCONCLUSIVE, alert)
    stats = await service.stats()
    assert stats.precision is None and stats.trainable == 0


@pytest.mark.asyncio
async def test_only_decisive_verdicts_become_training_rows():
    alerts = [_alert(user_id=f"u{i}") for i in range(4)]
    service, _, alert_repo = _service(alerts[0])
    for alert, verdict in zip(
        alerts,
        [
            Verdict.CONFIRMED_THREAT,
            Verdict.BENIGN,
            Verdict.POLICY_VIOLATION,
            Verdict.INCONCLUSIVE,
        ],
        strict=True,
    ):
        alert_repo.alert = alert
        await _record(service, verdict, alert)

    rows = await service.labelled_dataset()

    assert sorted(r.subject_user_id for r in rows) == ["u0", "u1"]
    assert {r.label for r in rows} == {True, False}
    # Each row carries the evidence, so it stays meaningful after retuning.
    assert all(r.detectors and r.model_version for r in rows)
