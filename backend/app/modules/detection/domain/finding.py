"""
ITBIS — Detection Module: findings

A finding is one detector's verdict about one person on one day: what kind of
anomaly it is, how severe (0-100), a readable explanation and the evidence
behind it. Findings feed the weighted insider risk score and alerts.

A finding is identified by (user, day, detector), so re-running detection over
the same day replaces it instead of adding a duplicate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.modules.detection.domain.categories import (
    CATEGORY_ENGINE,
    AnomalyCategory,
    DetectionEngine,
)

DETECTOR_VERSION = "detectors_v1"
_FINDING_NAMESPACE = uuid.UUID("5d6f1b0e-6c0a-4d4b-9a57-3f2f1f0d9e11")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def day_start(value: datetime) -> datetime:
    """Midnight UTC of the day `value` falls on."""
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass
class Finding:
    user_id: str
    day: datetime
    category: AnomalyCategory
    detector: str
    severity: float
    title: str
    description: str
    evidence: dict[str, Any] = field(default_factory=dict)
    event_ids: list[str] = field(default_factory=list)
    source_dataset: str = "all"
    detector_version: str = DETECTOR_VERSION
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.day = day_start(self.day)
        self.severity = round(max(0.0, min(100.0, float(self.severity))), 1)

    @property
    def engine(self) -> DetectionEngine:
        return CATEGORY_ENGINE[self.category]

    @property
    def key(self) -> str:
        return f"{self.user_id}|{self.day.date().isoformat()}|{self.detector}"

    @property
    def id(self) -> uuid.UUID:
        return uuid.uuid5(_FINDING_NAMESPACE, self.key)
