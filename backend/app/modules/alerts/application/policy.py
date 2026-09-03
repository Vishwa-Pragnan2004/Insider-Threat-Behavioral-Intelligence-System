"""
ITBIS — Alerts Module: Alert Generation Policy

Centralises the rule that decides whether an AnomalyResult should
produce an Alert.  Callers MUST go through `should_alert`; do not
hardcode risk-level thresholds in multiple places.

Default policy (configurable per instance):
    CRITICAL anomaly -> create CRITICAL alert
    HIGH anomaly     -> create HIGH alert
    MEDIUM anomaly   -> configurable (default: do NOT create)
    LOW anomaly      -> do NOT create

The policy also controls:
    - the minimum risk score required to generate an alert
    - whether to generate an alert when the anomaly prediction is
      `normal` (default: no — only act on `anomaly`)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.alerts.domain.enums import RISK_LEVEL_TO_SEVERITY, AlertSeverity
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel


@dataclass(frozen=True)
class AlertPolicy:
    """Immutable, configurable policy for converting anomaly results to alerts."""

    # The minimum risk level that produces an alert.  Anything below is
    # silently skipped.  Defaults to HIGH (matches the spec's "MEDIUM
    # does not create alerts by default" rule).
    minimum_risk_level: RiskLevel = RiskLevel.HIGH

    # Whether the anomaly prediction must be ANOMALY (vs NORMAL) for an
    # alert to be generated.  Defaults to True.
    require_anomaly_prediction: bool = True

    # Minimum risk_score required (independent of risk_level).  Defaults
    # to 0 (no additional threshold).
    minimum_risk_score: float = 0.0

    def should_alert(self, *, risk_level: RiskLevel, risk_score: float,
                     prediction: AnomalyPrediction) -> bool:
        if self.require_anomaly_prediction and prediction != AnomalyPrediction.ANOMALY:
            return False
        if risk_score < self.minimum_risk_score:
            return False
        # Risk-level comparison: each RiskLevel is `LOW < MEDIUM < HIGH < CRITICAL`.
        if not _risk_at_least(risk_level, self.minimum_risk_level):
            return False
        return True

    def severity_for(self, risk_level: RiskLevel) -> AlertSeverity:
        return RISK_LEVEL_TO_SEVERITY[risk_level]


# ─── Internal helpers ─────────────────────────────────────


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _risk_at_least(actual: RiskLevel, minimum: RiskLevel) -> bool:
    return _RISK_ORDER[actual] >= _RISK_ORDER[minimum]


# ─── Default policy ────────────────────────────────────────


DEFAULT_POLICY = AlertPolicy(
    minimum_risk_level=RiskLevel.HIGH,
    require_anomaly_prediction=True,
    minimum_risk_score=0.0,
)
