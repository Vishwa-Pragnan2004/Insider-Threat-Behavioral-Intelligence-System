"""
ITBIS — Unit tests: AlertPolicy

Covers:
  - severity mapping from risk level
  - HIGH anomaly -> generate alert
  - CRITICAL anomaly -> generate alert
  - MEDIUM anomaly does NOT generate alert by default
  - LOW anomaly does NOT generate alert
  - require_anomaly_prediction=True skips NORMAL predictions
  - minimum_risk_score enforced
  - boundary behaviour at the HIGH/MEDIUM threshold
"""


from app.modules.alerts.application.policy import (
    DEFAULT_POLICY,
    AlertPolicy,
)
from app.modules.alerts.domain.enums import AlertSeverity
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel

# ─── Severity mapping ─────────────────────────────────────


def test_default_policy_maps_critical_to_critical_severity():
    assert DEFAULT_POLICY.severity_for(RiskLevel.CRITICAL) == AlertSeverity.CRITICAL


def test_default_policy_maps_high_to_high_severity():
    assert DEFAULT_POLICY.severity_for(RiskLevel.HIGH) == AlertSeverity.HIGH


def test_default_policy_maps_medium_to_medium_severity():
    assert DEFAULT_POLICY.severity_for(RiskLevel.MEDIUM) == AlertSeverity.MEDIUM


def test_default_policy_maps_low_to_low_severity():
    assert DEFAULT_POLICY.severity_for(RiskLevel.LOW) == AlertSeverity.LOW


# ─── should_alert() ──────────────────────────────────────


def test_high_anomaly_with_default_policy_creates_alert():
    p = DEFAULT_POLICY
    assert p.should_alert(
        risk_level=RiskLevel.HIGH,
        risk_score=60.0,
        prediction=AnomalyPrediction.ANOMALY,
    )


def test_critical_anomaly_with_default_policy_creates_alert():
    p = DEFAULT_POLICY
    assert p.should_alert(
        risk_level=RiskLevel.CRITICAL,
        risk_score=80.0,
        prediction=AnomalyPrediction.ANOMALY,
    )


def test_medium_anomaly_with_default_policy_does_not_create_alert():
    p = DEFAULT_POLICY
    assert not p.should_alert(
        risk_level=RiskLevel.MEDIUM,
        risk_score=50.0,
        prediction=AnomalyPrediction.ANOMALY,
    )


def test_low_anomaly_with_default_policy_does_not_create_alert():
    p = DEFAULT_POLICY
    assert not p.should_alert(
        risk_level=RiskLevel.LOW,
        risk_score=20.0,
        prediction=AnomalyPrediction.ANOMALY,
    )


def test_normal_prediction_does_not_create_alert_by_default():
    """A HIGH risk score but NORMAL prediction should not alert when
    require_anomaly_prediction=True (the default)."""
    p = DEFAULT_POLICY
    assert not p.should_alert(
        risk_level=RiskLevel.HIGH,
        risk_score=70.0,
        prediction=AnomalyPrediction.NORMAL,
    )


def test_normal_prediction_does_create_alert_when_policy_relaxes():
    p = AlertPolicy(
        minimum_risk_level=RiskLevel.HIGH,
        require_anomaly_prediction=False,
    )
    assert p.should_alert(
        risk_level=RiskLevel.HIGH,
        risk_score=70.0,
        prediction=AnomalyPrediction.NORMAL,
    )


def test_minimum_risk_score_threshold_is_enforced():
    p = AlertPolicy(
        minimum_risk_level=RiskLevel.LOW,
        require_anomaly_prediction=False,
        minimum_risk_score=75.0,
    )
    assert not p.should_alert(
        risk_level=RiskLevel.CRITICAL,
        risk_score=74.999,
        prediction=AnomalyPrediction.ANOMALY,
    )
    assert p.should_alert(
        risk_level=RiskLevel.CRITICAL,
        risk_score=75.0,
        prediction=AnomalyPrediction.ANOMALY,
    )


def test_medium_threshold_can_be_lowered_to_generate_alerts():
    p = AlertPolicy(minimum_risk_level=RiskLevel.MEDIUM)
    assert p.should_alert(
        risk_level=RiskLevel.MEDIUM,
        risk_score=50.0,
        prediction=AnomalyPrediction.ANOMALY,
    )
    assert not p.should_alert(
        risk_level=RiskLevel.LOW,
        risk_score=20.0,
        prediction=AnomalyPrediction.ANOMALY,
    )


def test_policy_boundary_at_threshold():
    p = AlertPolicy(minimum_risk_level=RiskLevel.HIGH)
    # Exactly at threshold — should create (>= comparison).
    assert p.should_alert(
        risk_level=RiskLevel.HIGH,
        risk_score=60.0,
        prediction=AnomalyPrediction.ANOMALY,
    )
    # Just below — should NOT.
    assert not p.should_alert(
        risk_level=RiskLevel.MEDIUM,
        risk_score=59.9,
        prediction=AnomalyPrediction.ANOMALY,
    )
