"""
ITBIS — Unit tests: Alert generation service (deduplication, policy
filtering, manual backfill).

Uses in-memory fakes for both the alert repo and the anomaly store
(no SQL / Mongo).  The real Mongo + dedup path is covered by the
integration tests.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.modules.alerts.application.alert_generation_service import (
    AlertGenerationService,
    compute_idempotency_key,
)
from app.modules.alerts.application.policy import DEFAULT_POLICY, AlertPolicy
from app.modules.alerts.domain.entities import Alert
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.repositories import IAlertRepository
from app.modules.anomaly.domain.entities import AnomalyResult, BehavioralDeviation
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel
from app.modules.anomaly.domain.repositories import IAnomalyResultStore

# ─── Fakes ────────────────────────────────────────────────


class FakeAlertRepository(IAlertRepository):
    """
    In-memory alert store that enforces the unique idempotency_key
    invariant atomically — mimicking the real Mongo unique index.
    """

    def __init__(self) -> None:
        self.docs: dict[str, Alert] = {}  # idempotency_key -> Alert
        self.by_id: dict[uuid.UUID, Alert] = {}

    async def upsert(self, alert: Alert) -> tuple[Alert, bool]:
        existing = self.docs.get(alert.idempotency_key)
        if existing is not None:
            return existing, False
        self.docs[alert.idempotency_key] = alert
        self.by_id[alert.id] = alert
        return alert, True

    async def get_by_id(self, alert_id):
        return self.by_id.get(alert_id)

    async def _build_query(self, **kw):
        return kw

    async def list_alerts(self, **kwargs):
        items = list(self.docs.values())
        for k, v in kwargs.items():
            if v is None:
                continue
            if k in ("skip", "limit"):
                continue
            attr = {
                "status": "status",
                "severity": "severity",
                "user_id": "user_id",
                "assigned_to": "assigned_to",
                "risk_level": "risk_level",
                "source_dataset": "source_dataset",
                "investigation_id": "investigation_id",
            }.get(k, k)
            items = [a for a in items if getattr(a, attr, None) == v or (
                attr == "status" and getattr(a, attr) == v.value
            )]
        if kwargs.get("start") is not None:
            items = [a for a in items if a.created_at >= kwargs["start"]]
        if kwargs.get("end") is not None:
            items = [a for a in items if a.created_at < kwargs["end"]]
        items.sort(key=lambda a: a.created_at, reverse=True)
        return items[kwargs.get("skip", 0):][: kwargs.get("limit", 50)]

    async def count_alerts(self, **kwargs):
        items = await self.list_alerts(
            **{k: v for k, v in kwargs.items() if k not in ("skip", "limit")}
        )
        return len(items)

    async def update(self, alert: Alert) -> Alert:
        self.docs[alert.idempotency_key] = alert
        self.by_id[alert.id] = alert
        return alert


class FakeAnomalyResultStore(IAnomalyResultStore):
    def __init__(self, anomalies: list[AnomalyResult] | None = None) -> None:
        self.docs: list[AnomalyResult] = list(anomalies or [])

    async def upsert(self, result: AnomalyResult) -> None:
        self.docs.append(result)

    async def list_for_user(self, user_id, start=None, end=None, source_dataset=None, limit=100):
        return [d for d in self.docs if d.user_id == user_id]

    async def list_users_with_features(self, source_dataset=None):
        return sorted({d.user_id for d in self.docs})

    async def list_in_window(self, start=None, end=None, source_dataset=None):
        return list(self.docs)

    async def list_recent(self, risk_level=None, prediction=None, limit=100):
        out = list(self.docs)
        if risk_level is not None:
            out = [d for d in out if d.risk_level == risk_level]
        if prediction is not None:
            out = [d for d in out if d.prediction == prediction]
        return out[:limit]

    async def get_by_id(self, result_id):
        for d in self.docs:
            if d.id == result_id:
                return d
        return None


# ─── Anomaly factory ────────────────────────────────────


def _make_anomaly(
    *,
    user_id: str = "u1",
    risk_level: RiskLevel = RiskLevel.CRITICAL,
    risk_score: float = 85.0,
    prediction: AnomalyPrediction = AnomalyPrediction.ANOMALY,
    source_dataset: str = "cert",
    window: str = "daily",
    window_start: datetime | None = None,
    model_version: str = "itbis_behavior_v2",
) -> AnomalyResult:
    if window_start is None:
        window_start = datetime(2026, 8, 1, tzinfo=UTC)
    return AnomalyResult(
        user_id=user_id,
        source_dataset=source_dataset,
        window=window,
        window_start=window_start,
        window_end=datetime(2026, 8, 2, tzinfo=UTC),
        model_version=model_version,
        feature_version="behavioral_features_v1",
        prediction=prediction,
        raw_anomaly_score=-0.05,
        risk_score=risk_score,
        risk_level=risk_level,
        top_behavioral_deviations=[
            BehavioralDeviation(
                feature="usb_activity_count",
                value=10.0,
                baseline_mean=0.5,
                baseline_std=1.0,
                zscore=9.5,
            )
        ],
        model_input={},
        baseline_source="personal",
    )


# ─── Tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_critical_anomaly_creates_critical_alert():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore([_make_anomaly(risk_level=RiskLevel.CRITICAL)])
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    result = await svc.generate_for_anomaly(_make_anomaly(risk_level=RiskLevel.CRITICAL))

    assert result is not None
    assert result.severity == AlertSeverity.CRITICAL
    assert result.status == AlertStatus.OPEN
    assert result.risk_level == "CRITICAL"
    assert result.user_id == "u1"
    assert result.risk_score == 85.0
    assert len(alert_repo.docs) == 1


@pytest.mark.asyncio
async def test_high_anomaly_creates_high_alert():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    result = await svc.generate_for_anomaly(
        _make_anomaly(risk_level=RiskLevel.HIGH, risk_score=70.0)
    )

    assert result is not None
    assert result.severity == AlertSeverity.HIGH


@pytest.mark.asyncio
async def test_medium_anomaly_returns_none_by_default():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    result = await svc.generate_for_anomaly(
        _make_anomaly(risk_level=RiskLevel.MEDIUM, risk_score=50.0)
    )

    assert result is None
    assert len(alert_repo.docs) == 0


@pytest.mark.asyncio
async def test_low_anomaly_returns_none_by_default():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    result = await svc.generate_for_anomaly(
        _make_anomaly(risk_level=RiskLevel.LOW, risk_score=20.0)
    )

    assert result is None


@pytest.mark.asyncio
async def test_normal_prediction_does_not_create_alert_by_default():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    result = await svc.generate_for_anomaly(
        _make_anomaly(
            prediction=AnomalyPrediction.NORMAL,
            risk_level=RiskLevel.HIGH,
            risk_score=70.0,
        )
    )

    assert result is None


@pytest.mark.asyncio
async def test_duplicate_anomalies_collapse_to_one_alert():
    """Repeated detections of the same (user, window, start, model_version)
    must collapse to a single alert."""
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    anomaly = _make_anomaly()
    r1 = await svc.generate_for_anomaly(anomaly)
    r2 = await svc.generate_for_anomaly(anomaly)
    r3 = await svc.generate_for_anomaly(anomaly)

    assert r1 is not None
    assert r1.id == r2.id == r3.id  # same alert returned
    assert len(alert_repo.docs) == 1


@pytest.mark.asyncio
async def test_anomalies_with_different_windows_get_separate_alerts():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    a1 = _make_anomaly(window_start=datetime(2026, 8, 1, tzinfo=UTC))
    a2 = _make_anomaly(window_start=datetime(2026, 8, 2, tzinfo=UTC))

    r1 = await svc.generate_for_anomaly(a1)
    r2 = await svc.generate_for_anomaly(a2)

    assert r1.id != r2.id
    assert len(alert_repo.docs) == 2


@pytest.mark.asyncio
async def test_anomalies_with_different_model_versions_get_separate_alerts():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    a1 = _make_anomaly(model_version="v1")
    a2 = _make_anomaly(model_version="v2")

    r1 = await svc.generate_for_anomaly(a1)
    r2 = await svc.generate_for_anomaly(a2)

    assert r1.id != r2.id


@pytest.mark.asyncio
async def test_generated_alert_has_descriptive_title_and_explanation():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    anomaly = _make_anomaly(user_id="alice", risk_level=RiskLevel.CRITICAL)
    result = await svc.generate_for_anomaly(anomaly)

    assert "alice" in result.title
    assert "Critical" in result.title or "CRITICAL" in result.title
    # Description mentions the top deviation feature and its sigma.
    assert "usb_activity_count" in result.description
    assert "σ" in result.description


@pytest.mark.asyncio
async def test_generated_alert_links_anomaly_result_id():
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    anomaly = _make_anomaly()
    result = await svc.generate_for_anomaly(anomaly)

    assert result.anomaly_result_id == anomaly.id


@pytest.mark.asyncio
async def test_backfill_processes_existing_anomalies():
    alert_repo = FakeAlertRepository()
    anomalies = [
        _make_anomaly(risk_level=RiskLevel.CRITICAL, risk_score=85.0, user_id="alice"),
        _make_anomaly(risk_level=RiskLevel.HIGH, risk_score=70.0, user_id="bob"),
        _make_anomaly(risk_level=RiskLevel.MEDIUM, risk_score=50.0, user_id="carol"),
        _make_anomaly(risk_level=RiskLevel.LOW, risk_score=20.0, user_id="dave"),
    ]
    anomaly_repo = FakeAnomalyResultStore(anomalies)
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    result = await svc.generate_for_existing_anomalies(limit=100)

    assert result.created == 2
    assert result.skipped_below_threshold == 2
    assert result.total_processed == 4


@pytest.mark.asyncio
async def test_backfill_dedups_existing_alerts():
    """Running the backfill twice should not create duplicate alerts."""
    alert_repo = FakeAlertRepository()
    anomalies = [_make_anomaly()]
    anomaly_repo = FakeAnomalyResultStore(anomalies)
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=DEFAULT_POLICY)

    r1 = await svc.generate_for_existing_anomalies(limit=100)
    r2 = await svc.generate_for_existing_anomalies(limit=100)

    assert r1.created == 1
    assert r1.skipped_duplicates == 0
    assert r2.created == 0
    assert r2.skipped_duplicates == 1
    assert len(alert_repo.docs) == 1


@pytest.mark.asyncio
async def test_backfill_with_relaxed_policy_includes_medium():
    alert_repo = FakeAlertRepository()
    anomalies = [
        _make_anomaly(risk_level=RiskLevel.MEDIUM, user_id="carol"),
    ]
    anomaly_repo = FakeAnomalyResultStore(anomalies)
    policy = AlertPolicy(minimum_risk_level=RiskLevel.MEDIUM)
    svc = AlertGenerationService(alert_repo, anomaly_repo, policy=policy)

    result = await svc.generate_for_existing_anomalies(limit=100)
    assert result.created == 1


@pytest.mark.asyncio
async def test_idempotency_key_matches_call_directly():
    anomaly = _make_anomaly()
    expected = compute_idempotency_key(
        user_id=anomaly.user_id,
        window=anomaly.window,
        window_start=anomaly.window_start,
        model_version=anomaly.model_version,
    )
    alert_repo = FakeAlertRepository()
    anomaly_repo = FakeAnomalyResultStore()
    svc = AlertGenerationService(alert_repo, anomaly_repo)
    result = await svc.generate_for_anomaly(anomaly)
    assert result.idempotency_key == expected
