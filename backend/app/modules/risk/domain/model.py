"""
ITBIS — Risk Module: the weighted insider risk model

    Insider Risk Score =   Behavioral Anomalies          35%
                         + Privilege Misuse Indicators   25%
                         + Data Access Violations        20%
                         + Access Pattern Deviations     10%
                         + Historical Security Events    10%

Each component is itself 0-100, built from the signals (findings, model
results, past incidents) that belong to it, so the score is 0-100 and maps to
the same Low / Medium / High / Critical bands as everything else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.modules.anomaly.domain.enums import RiskLevel
from app.modules.detection.domain.categories import AnomalyCategory

RISK_MODEL_VERSION = "weighted_risk_v1"
_RISK_NAMESPACE = uuid.UUID("0b7f8a52-2c0e-4f55-8d25-7a3b1c9e4d60")


class RiskComponent(str, Enum):
    BEHAVIORAL_ANOMALIES = "behavioral_anomalies"
    PRIVILEGE_MISUSE = "privilege_misuse"
    DATA_ACCESS_VIOLATIONS = "data_access_violations"
    ACCESS_PATTERN_DEVIATIONS = "access_pattern_deviations"
    HISTORICAL_SECURITY_EVENTS = "historical_security_events"


RISK_WEIGHTS: dict[RiskComponent, float] = {
    RiskComponent.BEHAVIORAL_ANOMALIES: 0.35,
    RiskComponent.PRIVILEGE_MISUSE: 0.25,
    RiskComponent.DATA_ACCESS_VIOLATIONS: 0.20,
    RiskComponent.ACCESS_PATTERN_DEVIATIONS: 0.10,
    RiskComponent.HISTORICAL_SECURITY_EVENTS: 0.10,
}

COMPONENT_LABELS: dict[RiskComponent, str] = {
    RiskComponent.BEHAVIORAL_ANOMALIES: "Behavioral anomalies",
    RiskComponent.PRIVILEGE_MISUSE: "Privilege misuse indicators",
    RiskComponent.DATA_ACCESS_VIOLATIONS: "Data access violations",
    RiskComponent.ACCESS_PATTERN_DEVIATIONS: "Access pattern deviations",
    RiskComponent.HISTORICAL_SECURITY_EVENTS: "Historical security events",
}

CATEGORY_COMPONENT: dict[AnomalyCategory, RiskComponent] = {
    AnomalyCategory.BEHAVIORAL_ANOMALY: RiskComponent.BEHAVIORAL_ANOMALIES,
    AnomalyCategory.INSIDER_RISK_INDICATOR: RiskComponent.BEHAVIORAL_ANOMALIES,
    AnomalyCategory.PRIVILEGE_ABUSE: RiskComponent.PRIVILEGE_MISUSE,
    AnomalyCategory.ABNORMAL_DATA_DOWNLOAD: RiskComponent.DATA_ACCESS_VIOLATIONS,
    AnomalyCategory.EXCESSIVE_FILE_TRANSFER: RiskComponent.DATA_ACCESS_VIOLATIONS,
    AnomalyCategory.SUSPICIOUS_DEVICE_USAGE: RiskComponent.DATA_ACCESS_VIOLATIONS,
    AnomalyCategory.UNUSUAL_LOGIN_TIME: RiskComponent.ACCESS_PATTERN_DEVIATIONS,
    AnomalyCategory.UNAUTHORIZED_ACCESS_ATTEMPT: RiskComponent.ACCESS_PATTERN_DEVIATIONS,
}


@dataclass(frozen=True)
class RiskSignal:
    """Something that happened and bears on a person's risk."""

    day: datetime
    component: RiskComponent
    severity: float  # 0-100
    label: str
    category: AnomalyCategory | None = None
    reference: str | None = None  # finding key, anomaly result id, alert id…


@dataclass
class EmployeeRiskScore:
    user_id: str
    day: datetime
    score: float
    level: RiskLevel
    components: dict[RiskComponent, float]
    top_signals: list[dict[str, Any]] = field(default_factory=list)
    dominant_component: RiskComponent | None = None
    trend: float | None = None
    priority: float = 0.0
    model_version: str = RISK_MODEL_VERSION
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def key(self) -> str:
        return f"{self.user_id}|{self.day.date().isoformat()}"

    @property
    def id(self) -> uuid.UUID:
        return uuid.uuid5(_RISK_NAMESPACE, self.key)
