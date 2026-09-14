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
    risk_score_from_decision,
)
from app.modules.anomaly.domain.entities import BehavioralDeviation
from app.modules.anomaly.domain.enums import RiskLevel

# ─── risk_score_from_decision ─────────────────────────────

LOW, HIGH = -0.04, 0.25  # calibration percentiles in decision_function space


def test_decision_at_or_above_high_is_zero_risk():
    assert risk_score_from_decision(HIGH, LOW, HIGH) == 0.0
    assert risk_score_from_decision(1.0, LOW, HIGH) == 0.0


def test_decision_at_or_below_low_is_full_risk():
    assert risk_score_from_decision(LOW, LOW, HIGH) == 100.0
    assert risk_score_from_decision(-1.0, LOW, HIGH) == 100.0


def test_boundary_separates_low_from_medium():
    # Just inside normal stays LOW; just past the boundary is MEDIUM.
    assert classify_risk_level(risk_score_from_decision(0.0, LOW, HIGH)) == RiskLevel.LOW
    assert risk_score_from_decision(0.0, LOW, HIGH) == pytest.approx(39.99)
    assert classify_risk_level(risk_score_from_decision(-1e-6, LOW, HIGH)) == RiskLevel.MEDIUM


def test_halfway_to_low_is_high_risk():
    assert risk_score_from_decision(LOW / 2, LOW, HIGH) == pytest.approx(70.0)


def test_average_day_is_not_risky():
    """Regression: the old mapping scored every result, however ordinary, as 100."""
    assert classify_risk_level(risk_score_from_decision(0.064, LOW, HIGH)) == RiskLevel.LOW


def test_degenerate_bounds_stay_monotonic():
    scores = [risk_score_from_decision(d, 0.5, 0.5) for d in (0.6, 0.1, -0.1, -0.6)]
    assert scores == sorted(scores)
    assert scores[0] == 0.0 and scores[-1] == 100.0


def test_risk_rises_as_decision_falls():
    decisions = [0.30, 0.20, 0.10, 0.00, -0.01, -0.03, -0.10]
    scores = [risk_score_from_decision(d, LOW, HIGH) for d in decisions]
    assert scores == sorted(scores)


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
