"""
ITBIS — Anomaly Module: Risk Scoring

Maps the Isolation Forest's decision score to a 0-100 risk score and a risk
level (LOW / MEDIUM / HIGH / CRITICAL).

The decision score (`IsolationForest.decision_function`) is anchored on the
model's own boundary: >= 0 is normal, < 0 is anomalous. The artifact's
`score_low` / `score_high` are the 5th / 95th percentiles of that score on the
calibration data, so:

    normal   (decision >= 0): risk falls from just under 40 to 0 as the
                              decision rises to score_high
    anomaly  (decision <  0): risk rises from 40 to 100 as the decision falls
                              to score_low (and stays at 100 beyond it)

A normal prediction is therefore always LOW, and an anomaly is MEDIUM or above,
spread by how far past the boundary it falls.

Classification:
    LOW:       0 - 39
    MEDIUM:   40 - 59
    HIGH:     60 - 79
    CRITICAL: 80 - 100
"""
from __future__ import annotations

from app.modules.anomaly.domain.enums import RiskLevel

#: Anomalies start here; a normal prediction always scores below it.
ANOMALY_FLOOR = 40.0
_EPSILON = 1e-9


def risk_score_from_decision(decision: float, score_low: float, score_high: float) -> float:
    """
    Convert an Isolation Forest decision score to a 0-100 risk score.

    If a calibration bound sits on the wrong side of zero (degenerate
    calibration data), the other bound's magnitude stands in for it so the
    mapping stays monotonic.
    """
    normal_span = score_high if score_high > _EPSILON else max(abs(score_low), _EPSILON)
    anomaly_span = -score_low if score_low < -_EPSILON else max(abs(score_high), _EPSILON)
    if decision >= 0.0:
        closeness = min(decision / normal_span, 1.0)
        return round((ANOMALY_FLOOR - 0.01) * (1.0 - closeness), 3)
    severity = min(-decision / anomaly_span, 1.0)
    return round(ANOMALY_FLOOR + (100.0 - ANOMALY_FLOOR) * severity, 3)


def classify_risk_level(risk_score: float) -> RiskLevel:
    """Map a 0-100 risk score to a discrete RiskLevel."""
    if risk_score >= 80.0:
        return RiskLevel.CRITICAL
    if risk_score >= 60.0:
        return RiskLevel.HIGH
    if risk_score >= ANOMALY_FLOOR:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
