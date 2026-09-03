"""
ITBIS — Alerts Module: Domain Enums
"""
from enum import Enum

from app.modules.anomaly.domain.enums import RiskLevel


class AlertSeverity(str, Enum):
    """Severity of an alert.

    Mirrors the RiskLevel concept but is independent (an alert's
    severity is set at creation from the anomaly's risk_level and is
    not re-evaluated when the risk level is later re-classified).
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    """Lifecycle status of an alert.

    Lifecycle (valid transitions):
        OPEN
            -> ACKNOWLEDGED
            -> IN_PROGRESS
            -> RESOLVED
            -> FALSE_POSITIVE  (terminal — may also come from ACKNOWLEDGED)
        ACKNOWLEDGED
            -> IN_PROGRESS
            -> RESOLVED
            -> FALSE_POSITIVE
        IN_PROGRESS
            -> RESOLVED
            -> ACKNOWLEDGED   (analyst pulls it back)
        RESOLVED        (terminal)
        FALSE_POSITIVE  (terminal)
    """

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


# Risk-level → severity mapping.  Centralised so callers don't
# hardcode the mapping.
RISK_LEVEL_TO_SEVERITY: dict[RiskLevel, AlertSeverity] = {
    RiskLevel.LOW: AlertSeverity.LOW,
    RiskLevel.MEDIUM: AlertSeverity.MEDIUM,
    RiskLevel.HIGH: AlertSeverity.HIGH,
    RiskLevel.CRITICAL: AlertSeverity.CRITICAL,
}
