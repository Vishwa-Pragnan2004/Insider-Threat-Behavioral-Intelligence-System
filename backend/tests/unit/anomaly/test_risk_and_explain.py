"""
ITBIS — Unit tests for risk scoring and explainability.
"""
from __future__ import annotations

import pytest

from app.modules.anomaly.application.explainability import (
    format_deviation_line,
    top_deviations,
)
from app.modules.anomaly.application.risk_scoring import (
    classify_risk_level,
    normalize_to_risk_score,
)
from app.modules.anomaly.domain.entities import BehavioralDeviation
from app.modules.anomaly.domain.enums import RiskLevel

# ─── normalize_to_risk_score ──────────────────────────────


def test_normalize_zero_when_score_equals_high():
    # score == score_high → 0 (most normal)
    assert normalize_to_risk_score(0.25, score_low=-0.04, score_high=0.25) == 0.0


def test_normalize_100_when_score_equals_low():
    # score == score_low → 100 (most anomalous)
    assert normalize_to_risk_score(-0.04, score_low=-0.04, score_high=0.25) == 100.0


def test_normalize_midpoint_is_50():
    # score exactly halfway → 50
    midpoint = (-0.04 + 0.25) / 2
    assert (
        normalize_to_risk_score(midpoint, score_low=-0.04, score_high=0.25)
        == pytest.approx(50.0)
    )


def test_normalize_clamps_above_high():
    # Score more positive than score_high → clamped to 0
    assert normalize_to_risk_score(1.0, score_low=-0.04, score_high=0.25) == 0.0


def test_normalize_clamps_below_low():
    # Score more negative than score_low → clamped to 100
    assert normalize_to_risk_score(-1.0, score_low=-0.04, score_high=0.25) == 100.0


def test_normalize_handles_zero_range():
    # score_low == score_high → no signal → 0
    assert normalize_to_risk_score(0.0, score_low=0.5, score_high=0.5) == 0.0


def test_normalize_monotonic_with_anomaly():
    # More negative score → higher risk
    s_low, s_high = -0.04, 0.25
    r0 = normalize_to_risk_score(0.20, s_low, s_high)
    r1 = normalize_to_risk_score(0.10, s_low, s_high)
    r2 = normalize_to_risk_score(0.00, s_low, s_high)
    r3 = normalize_to_risk_score(-0.10, s_low, s_high)
    assert r0 < r1 < r2 < r3


# ─── classify_risk_level ──────────────────────────────────


def test_classify_low_below_40():
    assert classify_risk_level(0.0) == RiskLevel.LOW
    assert classify_risk_level(20.0) == RiskLevel.LOW
    assert classify_risk_level(39.9) == RiskLevel.LOW


def test_classify_medium_40_to_59():
    assert classify_risk_level(40.0) == RiskLevel.MEDIUM
    assert classify_risk_level(55.0) == RiskLevel.MEDIUM
    assert classify_risk_level(59.9) == RiskLevel.MEDIUM


def test_classify_high_60_to_79():
    assert classify_risk_level(60.0) == RiskLevel.HIGH
    assert classify_risk_level(70.0) == RiskLevel.HIGH
    assert classify_risk_level(79.9) == RiskLevel.HIGH


def test_classify_critical_80_to_100():
    assert classify_risk_level(80.0) == RiskLevel.CRITICAL
    assert classify_risk_level(95.0) == RiskLevel.CRITICAL
    assert classify_risk_level(100.0) == RiskLevel.CRITICAL


# ─── top_deviations ───────────────────────────────────────


def _dev(feature: str, z: float) -> BehavioralDeviation:
    return BehavioralDeviation(
        feature=feature,
        value=z,
        baseline_mean=0.0,
        baseline_std=1.0,
        zscore=z,
    )


def test_top_deviations_returns_top_n_by_abs_zscore():
    zscores = {
        "a": 0.5,
        "b": 3.0,
        "c": -2.0,
        "d": 1.0,
        "e": -5.0,
    }
    out = top_deviations(zscores, {}, {}, {}, top_n=3)
    assert [d.feature for d in out] == ["e", "b", "c"]


def test_top_deviations_uses_alphabetical_tiebreak():
    zscores = {"a": 1.0, "b": 1.0, "c": 1.0}
    out = top_deviations(zscores, {}, {}, {}, top_n=3)
    assert [d.feature for d in out] == ["a", "b", "c"]


def test_top_deviations_returns_all_when_n_larger_than_features():
    zscores = {"a": 1.0}
    out = top_deviations(zscores, {}, {}, {}, top_n=10)
    assert len(out) == 1


def test_top_deviations_preserves_signed_zscore():
    zscores = {"neg": -4.0, "pos": 2.0}
    out = top_deviations(zscores, {}, {}, {}, top_n=2)
    neg = next(d for d in out if d.feature == "neg")
    pos = next(d for d in out if d.feature == "pos")
    assert neg.zscore == -4.0
    assert pos.zscore == 2.0


def test_format_deviation_line_includes_feature_and_sigma():
    d = BehavioralDeviation(
        feature="usb_activity_count",
        value=5.0,
        baseline_mean=1.0,
        baseline_std=1.0,
        zscore=4.0,
    )
    line = format_deviation_line(d)
    assert "usb_activity_count" in line
    assert "+4.0" in line
    assert "σ" in line
