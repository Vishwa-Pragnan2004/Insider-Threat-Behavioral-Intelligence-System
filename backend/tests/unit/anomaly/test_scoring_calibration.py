"""
ITBIS — Unit tests: risk calibration and the learning period.

Covers:
  - ModelService scores in decision_function space; legacy artifacts
    calibrated on score_samples() have their bounds shifted on load
  - an ordinary CERT day is not flagged as risky
  - empty days are not scored
  - AlertPolicy learning period (no alerts without a personal baseline)
  - the pipeline rebuilds a personal baseline only when it is stale
"""
from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import joblib
import pytest

from app.modules.alerts.application.policy import DEFAULT_POLICY, AlertPolicy
from app.modules.anomaly.application.model_service import ModelService
from app.modules.anomaly.application.risk_scoring import classify_risk_level
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.exceptions import NoDataForBaselineError
from app.modules.ueba.application.detection_pipeline import LivePipelineStages
from tests.unit.anomaly.test_anomaly_detection_service import (  # noqa: F401 - fixtures
    PROJECT_ROOT,
    _make_row,
    baseline_repo,
    feature_store,
    model_service,
    result_store,
    service,
)

ARTIFACT = PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v2.joblib"
DAY = datetime(2026, 8, 1, tzinfo=UTC)


# ─── Scoring space ────────────────────────────────────────


def test_score_is_decision_function(model_service):  # noqa: F811
    art = model_service.get_artifact()
    vec = [[0.0] * len(art.model_features)]
    pred, raw = model_service.score(vec)
    assert (raw < 0) == (pred == -1), "decision_function sign matches predict()"


def test_legacy_score_samples_bounds_are_shifted_on_load(tmp_path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pkg = joblib.load(ARTIFACT)
    offset = float(pkg["model"].offset_)
    expected = ModelService(artifact_path=str(ARTIFACT)).get_artifact()

    pkg["score_low"] = expected.score_low + offset
    pkg["score_high"] = expected.score_high + offset
    pkg["metadata"] = {k: v for k, v in pkg["metadata"].items() if k != "score_space"}
    legacy = tmp_path / "legacy.joblib"
    joblib.dump(pkg, legacy)

    art = ModelService(artifact_path=str(legacy)).get_artifact()
    assert art.score_low == pytest.approx(expected.score_low)
    assert art.score_high == pytest.approx(expected.score_high)


@pytest.mark.asyncio
async def test_average_cert_day_is_low_risk(service, feature_store, model_service):  # noqa: F811
    means = model_service.get_artifact().global_means
    row = _make_row(values={n: float(means.get(n, 0.0)) for n in means}, window_start=DAY)
    row.event_count = 25
    feature_store.docs.append(row)

    result = await service.detect_for_user_window(
        user_id="alice", window_start=DAY, window_end=DAY + timedelta(days=1)
    )

    assert result.prediction == AnomalyPrediction.NORMAL
    assert classify_risk_level(result.risk_score) == RiskLevel.LOW


@pytest.mark.asyncio
async def test_empty_days_are_not_scored(service, feature_store, result_store):  # noqa: F811
    busy = _make_row(values={"logon_count": 3.0}, window_start=DAY,
                     window_end=DAY + timedelta(days=1))
    busy.event_count = 3
    empty = _make_row(window_start=DAY + timedelta(days=1),
                      window_end=DAY + timedelta(days=2))
    empty.event_count = 0
    feature_store.docs.extend([busy, empty])

    results = await service.detect_for_user(
        user_id="alice", start=DAY, end=DAY + timedelta(days=2), source_dataset="all"
    )

    assert [r.window_start for r in results] == [DAY]
    assert len(result_store.docs) == 1


# ─── Learning period ──────────────────────────────────────


def _critical(policy: AlertPolicy, baseline_source: str | None) -> bool:
    return policy.should_alert(
        risk_level=RiskLevel.CRITICAL,
        risk_score=95.0,
        prediction=AnomalyPrediction.ANOMALY,
        baseline_source=baseline_source,
    )


def test_default_policy_waits_for_a_personal_baseline():
    assert not _critical(DEFAULT_POLICY, "global")
    assert not _critical(DEFAULT_POLICY, None)
    assert _critical(DEFAULT_POLICY, "personal")


def test_learning_period_can_be_switched_off():
    assert _critical(AlertPolicy(require_personal_baseline=False), "global")


# ─── Pipeline baseline refresh ────────────────────────────


class FakeFeatureService:
    def __init__(self, existing=None, error: Exception | None = None) -> None:
        self.existing = existing
        self.error = error
        self.builds: list[dict] = []

    async def get_baseline(self, user_id, feature_version=FEATURE_VERSION):
        return self.existing

    async def build_baseline(self, **kwargs):
        self.builds.append(kwargs)
        if self.error:
            raise self.error


def _stages() -> LivePipelineStages:
    return LivePipelineStages(None, None, None, baseline_history_days=28, baseline_min_days=5)


@pytest.mark.asyncio
async def test_baseline_is_built_from_history_before_the_window():
    fake = FakeFeatureService()

    assert await _stages().refresh_baseline(fake, "alice", DAY) is True

    [build] = fake.builds
    assert build["history_start"] == DAY - timedelta(days=28)
    assert build["history_end"] == DAY, "the scored window never feeds its own baseline"
    assert build["min_observation_days"] == 5


@pytest.mark.asyncio
async def test_fresh_baseline_is_not_rebuilt():
    # SQL hands back naive datetimes; they are UTC.
    fake = FakeFeatureService(existing=SimpleNamespace(window_end=DAY.replace(tzinfo=None)))

    assert await _stages().refresh_baseline(fake, "alice", DAY) is False
    assert fake.builds == []


@pytest.mark.asyncio
async def test_stale_baseline_is_rebuilt_and_too_little_history_is_not_an_error():
    stale = SimpleNamespace(window_end=DAY - timedelta(days=1))
    fake = FakeFeatureService(existing=stale, error=NoDataForBaselineError("2 active days"))

    assert await _stages().refresh_baseline(fake, "alice", DAY) is False
    assert len(fake.builds) == 1


def test_batch_scoring_matches_row_by_row(model_service):  # noqa: F811
    width = len(model_service.get_artifact().model_features)
    rows = [[0.0] * width, [5.0] * width, [50.0] * width]
    predictions, scores = model_service.score_many(rows)
    for row, pred, score in zip(rows, predictions, scores, strict=True):
        single_pred, single_score = model_service.score([row])
        assert pred == single_pred and score == pytest.approx(single_score)
    assert model_service.score_many([]) == ([], [])
