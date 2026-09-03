"""
ITBIS — Anomaly Module: Risk Scoring

Maps the Isolation Forest's raw score to a 0-100 risk score and a
risk level (LOW / MEDIUM / HIGH / CRITICAL).

The artifact's `score_low` and `score_high` are the fitted bounds of
the score distribution seen during training:

  - `score_high`  =  most *normal* score (least anomalous)
  - `score_low`   =  most *anomalous* score (most anomalous)

Lower (more negative) raw scores = more anomalous.  The risk score
is therefore:

    risk_score = 100 * (score_high - raw) / (score_high - score_low)
                 clamped to [0, 100]

Classification:

    LOW:      0  - 39
    MEDIUM:  40  - 59
    HIGH:    60  - 79
    CRITICAL: 80 -100
"""
from __future__ import annotations

from app.modules.anomaly.domain.enums import RiskLevel


def normalize_to_risk_score(
    raw_score: float,
    score_low: float,
    score_high: float,
) -> float:
    """Convert an Isolation Forest raw score to a 0-100 risk score.

    Higher = more anomalous.  Clamped to [0, 100].

    Defensive against degenerate `score_high == score_low` (returns 0.0
    rather than dividing by zero).
    """
    if score_high == score_low:
        return 0.0
    raw = max(min(raw_score, score_high), score_low)
    risk = 100.0 * (score_high - raw) / (score_high - score_low)
    if risk < 0.0:
        return 0.0
    if risk > 100.0:
        return 100.0
    return float(risk)


def classify_risk_level(risk_score: float) -> RiskLevel:
    """Map a 0-100 risk score to a discrete RiskLevel."""
    if risk_score >= 80.0:
        return RiskLevel.CRITICAL
    if risk_score >= 60.0:
        return RiskLevel.HIGH
    if risk_score >= 40.0:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
