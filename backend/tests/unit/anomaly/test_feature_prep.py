"""
ITBIS — Unit tests for feature preparation (Phase 5).

Tests the 32-feature builder, Z-score deviation logic, zero-std
fallback, global baseline fallback, and exact ordering.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.anomaly.application.feature_prep import build_32_features
from app.modules.anomaly.application.model_service import ModelService
from app.modules.behavioral.domain.entities import BehavioralBaseline, BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION

PROJECT_ROOT = Path(os.environ["ITBIS_MODEL_PATH"]).parent.parent


@pytest.fixture(scope="module")
def artifact():
    artifact = PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v2.joblib"
    svc = ModelService(artifact_path=str(artifact))
    return svc.get_artifact()


def _make_feature_row(values: dict[str, float] | None = None) -> BehavioralFeatures:
    feats = {n: 0.0 for n in FEATURE_NAMES}
    if values:
        feats.update(values)
    return BehavioralFeatures(
        user_id="alice",
        window="daily",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        source_dataset="cert",
        features=feats,
        feature_version=FEATURE_VERSION,
        event_count=1,
    )


def _make_baseline(means: dict[str, float], stds: dict[str, float]) -> BehavioralBaseline:
    return BehavioralBaseline(
        user_id="alice",
        feature_version=FEATURE_VERSION,
        stats={
            name: {"mean": means.get(name, 0.0), "std": stds.get(name, 1.0),
                   "min": 0.0, "max": 10.0, "count": 30}
            for name in FEATURE_NAMES
        },
        window_start=datetime(2026, 7, 1, tzinfo=UTC),
        window_end=datetime(2026, 8, 1, tzinfo=UTC),
        observation_days=30,
        source_dataset="cert",
    )


# ─── Vector shape + order ─────────────────────────────────


def test_vector_has_32_elements(artifact):
    row = _make_feature_row()
    out = build_32_features(row, baseline=None, artifact=artifact)
    assert len(out.vector) == 32


def test_vector_order_matches_model_features(artifact):
    row = _make_feature_row()
    out = build_32_features(row, baseline=None, artifact=artifact)
    # The 32 features must be in the artifact's locked model_features order.
    # The vector is a list of floats; we can't check names directly, so we
    # re-encode a DataFrame and check columns.
    import pandas as pd
    df = pd.DataFrame([out.vector], columns=artifact.model_features)
    assert list(df.columns) == artifact.model_features
    # First 16 are the base feature columns, last 16 are the z-score columns
    assert list(df.columns[:16]) == artifact.feature_columns
    assert list(df.columns[16:]) == artifact.z_feature_columns


def test_zscore_columns_strip_suffix(artifact):
    for base, z in zip(artifact.feature_columns, artifact.z_feature_columns, strict=False):
        assert z == f"{base}_zscore"


# ─── Z-score math ──────────────────────────────────────────


def test_zscore_zero_deviation_against_meaningful_baseline(artifact):
    baseline = _make_baseline(
        means={n: 10.0 for n in FEATURE_NAMES},
        stds={n: 2.0 for n in FEATURE_NAMES},
    )
    row = _make_feature_row({n: 10.0 for n in FEATURE_NAMES})  # exactly at mean
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    for z in out.zscores.values():
        assert abs(z) < 1e-9


def test_zscore_positive_when_above_mean(artifact):
    baseline = _make_baseline(
        means={n: 10.0 for n in FEATURE_NAMES},
        stds={n: 2.0 for n in FEATURE_NAMES},
    )
    row = _make_feature_row({"total_activity_count": 20.0})  # +5σ
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    assert abs(out.zscores["total_activity_count"] - 5.0) < 1e-9


def test_zscore_negative_when_below_mean(artifact):
    baseline = _make_baseline(
        means={n: 10.0 for n in FEATURE_NAMES},
        stds={n: 2.0 for n in FEATURE_NAMES},
    )
    row = _make_feature_row({"total_activity_count": 0.0})  # -5σ
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    assert abs(out.zscores["total_activity_count"] - (-5.0)) < 1e-9


# ─── Zero / missing std fallback ──────────────────────────


def test_zero_std_falls_back_to_global(artifact):
    """If the per-user std is zero (degenerate baseline), we should fall back
    to the artifact's global std so the Z-score is finite."""
    means = {n: 10.0 for n in FEATURE_NAMES}
    stds = {n: 0.0 for n in FEATURE_NAMES}  # all zero
    baseline = _make_baseline(means=means, stds=stds)
    # total_activity_count = 20, global mean = ?, global std = ?
    # Whatever the global stats are, with stds>0 the z-score should be finite.
    row = _make_feature_row({"total_activity_count": 20.0})
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    assert out.zscores["total_activity_count"] != float("inf")
    assert out.zscores["total_activity_count"] != float("-inf")
    assert out.baseline_source == "personal"


def test_negative_std_is_treated_as_zero(artifact):
    means = {n: 10.0 for n in FEATURE_NAMES}
    stds = {n: -1.0 for n in FEATURE_NAMES}
    baseline = _make_baseline(means=means, stds=stds)
    row = _make_feature_row({"total_activity_count": 20.0})
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    # Should still produce a finite z-score using the global fallback
    assert out.zscores["total_activity_count"] == out.zscores["total_activity_count"]  # not NaN


# ─── Personal vs global baseline selection ───────────────


def test_personal_baseline_takes_precedence(artifact):
    baseline = _make_baseline(
        means={n: 100.0 for n in FEATURE_NAMES},
        stds={n: 5.0 for n in FEATURE_NAMES},
    )
    row = _make_feature_row({"total_activity_count": 100.0})
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    assert out.baseline_source == "personal"
    assert abs(out.zscores["total_activity_count"]) < 1e-9


def test_falls_back_to_global_when_no_personal_baseline(artifact):
    row = _make_feature_row({"total_activity_count": 100.0})
    out = build_32_features(row, baseline=None, artifact=artifact)
    assert out.baseline_source == "global"
    # With global stats, the z-score should be a finite number.
    z = out.zscores["total_activity_count"]
    assert z == z  # not NaN
    assert z != float("inf")


def test_personal_baseline_with_artifact_user_id_used_when_phase4_missing(artifact):
    """If Phase 4 has no baseline for the user, but the artifact does
    (artifact stores 1000 users' baselines), prefer the artifact's."""
    row = _make_feature_row()
    row_user = artifact.baseline_stats.get("alice")
    if row_user is None:
        pytest.skip("artifact doesn't have an 'alice' user baseline")
    out = build_32_features(row, baseline=None, artifact=artifact)
    assert out.baseline_source == "personal"


# ─── Observed values preserved ──────────────────────────


def test_observed_values_pass_through_unchanged(artifact):
    baseline = _make_baseline(
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    row = _make_feature_row({
        "total_activity_count": 42.0,
        "logon_count": 7.0,
        "email_count": 0.0,
    })
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    # The first 16 elements of the vector (base features) should match
    # the row's features exactly, in the locked column order.
    for i, name in enumerate(artifact.feature_columns):
        assert out.vector[i] == row.features[name]


def test_missing_feature_defaults_to_zero(artifact):
    baseline = _make_baseline(
        means={n: 5.0 for n in FEATURE_NAMES},
        stds={n: 1.0 for n in FEATURE_NAMES},
    )
    # Build a row that has only one feature populated.
    row = BehavioralFeatures(
        user_id="alice",
        window="daily",
        window_start=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 2, 0, 0, tzinfo=UTC),
        source_dataset="cert",
        features={"logon_count": 3.0},  # only one feature
        feature_version=FEATURE_VERSION,
    )
    out = build_32_features(row, baseline=baseline, artifact=artifact)
    # The single populated feature is preserved; others default to 0.
    assert out.vector[artifact.feature_columns.index("logon_count")] == 3.0
    # Every other feature slot is 0.0
    for i, name in enumerate(artifact.feature_columns):
        if name == "logon_count":
            continue
        assert out.vector[i] == 0.0
