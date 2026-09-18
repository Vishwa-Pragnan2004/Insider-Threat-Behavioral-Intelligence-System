"""
ITBIS — Feedback Module: Domain Entities

An `AnalystVerdict` is one analyst's judgement of one alert, together
with a snapshot of what the system believed when it raised that alert.

The snapshot is the point.  A label on its own ("user X on day Y was a
real threat") is almost useless for training later, because by then the
detectors, the weights and the model will all have moved.  Knowing that
the system scored the day at priority 82, under model v3, citing these
three detectors, and that an analyst said it was right, is a fact that
stays true.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from app.modules.feedback.domain.enums import TRAINING_LABEL, Verdict


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class EvidenceSnapshot:
    """What the system believed about the subject when the alert was raised."""

    #: "behavioral_model" or "insider_risk".
    source: str
    severity: str
    #: Weighted insider risk score, and the queue priority derived from it.
    risk_score: float | None
    priority: float | None
    model_version: str
    feature_version: str
    #: Detectors that fired on the day, e.g. ["suspicious_device_usage"].
    detectors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)


@dataclass
class AnalystVerdict:
    """One recorded judgement.

    Verdicts are never edited in place.  A correction is a new verdict
    that supersedes the old one, so the record of what was believed and
    when it changed survives — an analyst revising a call months later is
    information, not a mistake to be overwritten.
    """

    alert_id: uuid.UUID
    #: Who the alert was about, and the day it covered.
    subject_user_id: str
    subject_day: date
    verdict: Verdict
    #: Free text.  Required for every verdict: a label nobody can explain
    #: is a label nobody can audit.
    rationale: str
    decided_by: str
    evidence: EvidenceSnapshot

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    decided_at: datetime = field(default_factory=_utcnow)
    #: Set when a later verdict replaces this one.
    superseded_at: datetime | None = None
    superseded_by: uuid.UUID | None = None

    @property
    def is_current(self) -> bool:
        return self.superseded_at is None

    @property
    def training_label(self) -> bool | None:
        """True (threat), False (benign), or None — excluded from training."""
        return TRAINING_LABEL[self.verdict]

    def supersede(self, replacement_id: uuid.UUID) -> None:
        self.superseded_at = _utcnow()
        self.superseded_by = replacement_id
