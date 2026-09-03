"""
ITBIS — Unit tests for the AnomalyDetectionService orchestrator.

Uses fakes for the feature store, baseline repo, and result store so
no SQL/Mongo is required.  The real model artifact is loaded once
(session scope) so these tests exercise the actual sklearn inference.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.modules.anomaly.application.anomaly_detection_service import (
    AnomalyDetectionService,
)
from app.modules.anomaly.application.model_service import ModelService
from app.modules.anomaly.domain.entities import AnomalyResult
from app.modules.anomaly.domain.enums import RiskLevel
from app.modules.anomaly.domain.exceptions import NoDataForDetectionError
from app.modules.anomaly.domain.repositories import IAnomalyResultStore
from app.modules.behavioral.domain.entities import (
    BehavioralBaseline,
    BehavioralFeatures,
)
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.behavioral.domain.repositories import (
    IBehavioralBaselineRepository,
    IBehavioralFeatureStore,
)

PROJECT_ROOT = Path(os.environ["ITBIS_MODEL_PATH"]).parent.parent

# ─── Fakes ────────────────────────────────────────────────


class FakeFeatureStore(IBehavioralFeatureStore):
    def __init__(self, rows: list[BehavioralFeatures] | None = None) -> None:
        self.docs: list[BehavioralFeatures] = list(rows or [])

    async def upsert_many(self, features):
        self.docs.extend(features)
        return len(features)

    async def list_for_user(self, user_id, start=None, end=None, source_dataset=None):
        return [
            d for d in self.docs
            if d.user_id == user_id
            and (start is None or d.window_start >= start)
            and (end is None or d.window_start < end)
            and (source_dataset is None or d.source_dataset == source_dataset)
        ]

    async def list_users_with_features(self, source_dataset=None):
        return sorted({d.user_id for d in self.docs})

    async def list_in_window(self, start=None, end=None, source_dataset=None):
        return [
            d for d in self.docs
            if (start is None or d.window_start >= start)
            and (end is None or d.window_start < end)
            and (source_dataset is None or d.source_dataset == source_dataset)
        ]


class FakeBaselineRepo(IBehavioralBaselineRepository):
    def __init__(self, baselines: dict[str, BehavioralBaseline] | None = None) -> None:
        self.baselines: dict[str, BehavioralBaseline] = dict(baselines or {})

    async def save(self, baseline: BehavioralBaseline) -> BehavioralBaseline:
        self.baselines[(baseline.user_id, baseline.feature_version)] = baseline
        return baseline

    async def get(self, user_id, feature_version):
        return self.baselines.get((user_id, feature_version))

    async def list_all(self):
        return list(self.baselines.values())


class FakeResultStore(IAnomalyResultStore):
    def __init__(self) -> None:
        self.docs: list[AnomalyResult] = []

    async def upsert(self, result: AnomalyResult) -> None:
        # Replace any existing row with the same (user, window, start)
        self.docs = [
            r for r in self.docs
            if not (r.user_id == result.user_id
                    and r.window == result.window
                    and r.window_start == result.window_start)
        ]
        self.docs.append(result)

    async def list_for_user(self, user_id, start=None, end=None,
                            risk_level=None, limit=100):
        return [
            d for d in self.docs
            if d.user_id == user_id
            and (start is None or d.window_start >= start)
            and (end is None or d.window_start < end)
            and (risk_level is None or d.risk_level == risk_level)
        ][:limit]

    async def list_recent(self, risk_level=None, prediction=None, limit=100):
        out = self.docs
        if risk_level is not None:
            out = [d for d in out if d.risk_level == risk_level]
        if prediction is not None:
            out = [d for d in out if d.prediction == prediction]
        return out[:limit]

    async def get_by_id(self, result_id):
        for d in self.docs:
            if str(d.id) == str(result_id):
                return d
        return None


# ─── Fixtures ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def model_service() -> ModelService:
    artifact = PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v2.joblib"
    return ModelService(artifact_path=str(artifact))


def _make_row(
    user_id: str = "alice",
    *,
    values: dict[str, float] | None = None,
    source: str = "cert",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> BehavioralFeatures:
    feats = {n: 0.0 for n in FEATURE_NAMES}
    if values:
        feats.update(values)
    return BehavioralFeatures(
        user_id=user_id,
        window="daily",
        window_start=window_start or datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=window_end or datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        source_dataset=source,
        features=feats,
        feature_version=FEATURE_VERSION,
        event_count=1,
    )


def _make_baseline(
    user_id: str,
    means: dict[str, float],
    stds: dict[str, float],
) -> BehavioralBaseline:
    return BehavioralBaseline(
        user_id=user_id,
        feature_version=FEATURE_VERSION,
        stats={
            n: {"mean": means.get(n, 0.0), "std": stds.get(n, 1.0),
                "min": 0.0, "max": 10.0, "count": 30}
            for n in FEATURE_NAMES
        },
        window_start=datetime(2026, 7, 1, tzinfo=UTC),
        window_end=datetime(2026, 8, 1, tzinfo=UTC),
        observation_days=30,
        source_dataset="cert",
    )


@pytest.fixture
def feature_store() -> FakeFeatureStore:
    return FakeFeatureStore()


@pytest.fixture
def baseline_repo() -> FakeBaselineRepo:
    return FakeBaselineRepo()


@pytest.fixture
def result_store() -> FakeResultStore:
    return FakeResultStore()


@pytest.fixture
def service(
    model_service: ModelService,
    feature_store: FakeFeatureStore,
    baseline_repo: FakeBaselineRepo,
    result_store: FakeResultStore,
) -> AnomalyDetectionService:
    return AnomalyDetectionService(
        model_service=model_service,
        feature_store=feature_store,
        baseline_repo=baseline_repo,
        result_store=result_store,
    )


# ─── FIX 1: alert observer failure handling ─────────────────


@pytest.fixture
def service_with_observer(
    model_service: ModelService,
    feature_store: FakeFeatureStore,
    baseline_repo: FakeBaselineRepo,
    result_store: FakeResultStore,
):
    """
    Build a service with a healthy alert observer.  Returns
    (service, calls_list, results_list) so tests can inspect how
    many times the observer was called and what it saw.
    """
    calls: list = []
    results: list = []

    async def healthy_observer(anomaly):
        calls.append(anomaly)
        results.append(anomaly)
        return None

    svc = AnomalyDetectionService(
        model_service=model_service,
        feature_store=feature_store,
        baseline_repo=baseline_repo,
        result_store=result_store,
        alert_observer=healthy_observer,
    )
    return svc, calls, results


@pytest.fixture
def service_with_raising_observer(
    model_service: ModelService,
    feature_store: FakeFeatureStore,
    baseline_repo: FakeBaselineRepo,
    result_store: FakeResultStore,
):
    """
    Build a service whose alert observer ALWAYS raises.  Returns
    (service, calls_list) so tests can verify the observer was
    attempted but the exception was swallowed.
    """
    calls: list = []

    async def raising_observer(anomaly):  # type: ignore[no-untyped-def]
        calls.append(anomaly)
        raise RuntimeError("simulated alert generation failure")

    svc = AnomalyDetectionService(
        model_service=model_service,
        feature_store=feature_store,
        baseline_repo=baseline_repo,
        result_store=result_store,
        alert_observer=raising_observer,
    )
    return svc, calls


# ─── End-to-end orchestration ─────────────────────────────


@pytest.mark.asyncio
async def test_detect_for_user_window_produces_result(
    service, feature_store, baseline_repo, result_store
):
    feature_store.docs.append(_make_row(values={"logon_count": 5.0}))
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 2.0 for n in FEATURE_NAMES},
    )
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    assert isinstance(result, AnomalyResult)
    assert result.user_id == "alice"
    assert result.risk_score >= 0.0
    assert result.risk_score <= 100.0
    assert result.risk_level in (
        RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL,
    )
    # The result is persisted by default
    assert len(result_store.docs) == 1


@pytest.mark.asyncio
async def test_detect_high_activity_is_more_anomalous(
    service, feature_store, baseline_repo
):
    feature_store.docs.append(_make_row(values={n: 100.0 for n in FEATURE_NAMES}))
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    # Way outside the baseline — must be high risk.
    assert result.risk_score >= 60.0
    assert result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


@pytest.mark.asyncio
async def test_detect_normal_activity_scores_lower_than_extreme(
    service, feature_store, baseline_repo
):
    """We don't assert the absolute level of 'normal' risk — the
    trained model has a complex score distribution — but we do verify
    that a high-z-score input is strictly more anomalous than a
    near-mean input.
    """
    import warnings

    import joblib
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pkg = joblib.load(
            r"C:\Users\vishw\Desktop\spring\2\project2\ml_model\itbis_behavior_model_v2.joblib"
        )
    global_means = pkg["global_means"]
    global_stds = pkg["global_stds"]

    # First: a near-mean vector (z-scores ≈ 0)
    near_mean = {n: round(global_means.get(n, 5.0)) for n in FEATURE_NAMES}
    feature_store.docs.append(
        _make_row(
            user_id="alice",
            window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
            window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
            values=near_mean,
        )
    )
    # Second: an extreme vector (z-scores very large)
    extreme = {n: 100.0 for n in FEATURE_NAMES}
    feature_store.docs.append(
        _make_row(
            user_id="alice",
            window_start=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
            window_end=datetime(2026, 8, 3, 0, 0, tzinfo=UTC),
            values=extreme,
        )
    )
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: global_means.get(n, 5.0) for n in FEATURE_NAMES},
        stds={n: global_stds.get(n, 1.0) for n in FEATURE_NAMES},
    )
    results = await service.detect_for_user(
        user_id="alice",
        start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        end=datetime(2026, 8, 3, 0, 0, tzinfo=UTC),
    )
    by_day = {r.window_start: r for r in results}
    near_mean_score = by_day[
        datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    ].raw_anomaly_score
    extreme_score = by_day[
        datetime(2026, 8, 2, 0, 0, tzinfo=UTC)
    ].raw_anomaly_score
    # Isolation Forest: more negative = more anomalous.
    assert extreme_score < near_mean_score


@pytest.mark.asyncio
async def test_detect_missing_data_raises(
    service, feature_store, baseline_repo
):
    with pytest.raises(NoDataForDetectionError):
        await service.detect_for_user_window(
            user_id="ghost",
            window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
            window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_detect_with_personal_baseline_marks_source(
    service, feature_store, baseline_repo
):
    feature_store.docs.append(_make_row(values={n: 5.0 for n in FEATURE_NAMES}))
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    assert result.baseline_source == "personal"


@pytest.mark.asyncio
async def test_detect_falls_back_to_global_baseline_when_no_phase4(
    service, feature_store
):
    feature_store.docs.append(_make_row(values={n: 5.0 for n in FEATURE_NAMES}))
    # No baseline_repo.baselines entry — should use artifact's global
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    assert result.baseline_source in ("personal", "global")
    # If the artifact has a baseline for "alice" we should have used it
    # (test_artifact_baselines_personal_pref checks this elsewhere).
    # Otherwise we fell back to global.
    assert result.risk_score >= 0.0


@pytest.mark.asyncio
async def test_detect_persists_top_behavioral_deviations(
    service, feature_store, baseline_repo
):
    feature_store.docs.append(_make_row(values={"usb_activity_count": 50.0, "logon_count": 3.0}))
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    assert len(result.top_behavioral_deviations) == 3
    # Top deviation is usb_activity_count (z = 45)
    assert result.top_behavioral_deviations[0].feature == "usb_activity_count"


@pytest.mark.asyncio
async def test_detect_model_input_preserves_32_values(
    service, feature_store, baseline_repo
):
    feature_store.docs.append(_make_row())
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    assert len(result.model_input) == 32


@pytest.mark.asyncio
async def test_detect_for_user_returns_one_result_per_row(
    service, feature_store
):
    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    for d in range(3):
        feature_store.docs.append(
            _make_row(window_start=base + timedelta(days=d),
                      window_end=base + timedelta(days=d + 1),
                      values={"logon_count": 3.0})
        )
    results = await service.detect_for_user(
        user_id="alice",
        start=base,
        end=base + timedelta(days=3),
    )
    assert len(results) == 3
    assert all(r.user_id == "alice" for r in results)


@pytest.mark.asyncio
async def test_detect_can_skip_persistence(
    service, feature_store, baseline_repo, result_store
):
    feature_store.docs.append(_make_row())
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        persist=False,
    )
    assert len(result_store.docs) == 0


# ─── FIX 1: alert observer failure handling ─────────────────


@pytest.mark.asyncio
async def test_anomaly_detect_succeeds_when_alert_observer_succeeds(
    service_with_observer, feature_store, baseline_repo, result_store
):
    """Sanity check: a healthy observer does not break detection."""
    service, observer_calls, _observer_result = service_with_observer
    feature_store.docs.append(_make_row())
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    assert result is not None
    # The healthy observer was called exactly once.
    assert len(observer_calls) == 1
    # The anomaly result is still persisted.
    assert len(result_store.docs) == 1


@pytest.mark.asyncio
async def test_anomaly_detect_succeeds_when_alert_observer_raises(
    service_with_raising_observer, feature_store, baseline_repo, result_store
):
    """
    FIX 1: if the alert-generation observer raises, anomaly detection
    must still succeed and the anomaly result must still be persisted.
    """
    service, raising_calls = service_with_raising_observer
    feature_store.docs.append(_make_row())
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    # Detection must NOT raise even though the observer raises.
    result = await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    # The anomaly result is returned successfully.
    assert result is not None
    # The anomaly result is still persisted in the result store.
    assert len(result_store.docs) == 1
    # The observer was attempted.
    assert len(raising_calls) == 1


@pytest.mark.asyncio
async def test_alert_observer_exception_is_logged(
    service_with_raising_observer, feature_store, baseline_repo, caplog
):
    """
    FIX 1: when the observer raises, the exception must be logged
    with sufficient context (not silently swallowed).
    """
    import logging

    caplog.set_level(logging.ERROR, logger="app.modules.anomaly")
    service, _ = service_with_raising_observer
    feature_store.docs.append(_make_row())
    baseline_repo.baselines[("alice", FEATURE_VERSION)] = _make_baseline(
        "alice",
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    await service.detect_for_user_window(
        user_id="alice",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
    )
    # The structured log must have been emitted.
    matches = [
        record
        for record in caplog.records
        if "anomaly.alert_observer_raised" in (record.message or "")
    ]
    assert matches, (
        "Expected a log record for 'anomaly.alert_observer_raised' "
        f"in {[r.message for r in caplog.records]}"
    )
