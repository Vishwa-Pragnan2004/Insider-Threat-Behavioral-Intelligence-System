"""
ITBIS — Anomaly Module: Domain Enums
"""
from enum import Enum


class RiskLevel(str, Enum):
    """Risk level assigned to a detection result.

    Thresholds (per project spec):
        LOW:      0-39
        MEDIUM:  40-59
        HIGH:    60-79
        CRITICAL: 80-100
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AnomalyPrediction(str, Enum):
    """The Isolation Forest binary decision, projected to a domain enum."""

    NORMAL = "normal"
    ANOMALY = "anomaly"
