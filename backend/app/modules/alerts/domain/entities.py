"""
ITBIS — Alerts Module: Domain Entities
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus


def _utcnow() -> datetime:
    from datetime import UTC
    return datetime.now(UTC)


# ─── Lifecycle helpers ─────────────────────────────────────


_VALID_TRANSITIONS: dict[AlertStatus, set[AlertStatus]] = {
    AlertStatus.OPEN: {
        AlertStatus.ACKNOWLEDGED,
        AlertStatus.IN_PROGRESS,
        AlertStatus.RESOLVED,
        AlertStatus.FALSE_POSITIVE,
    },
    AlertStatus.ACKNOWLEDGED: {
        AlertStatus.IN_PROGRESS,
        AlertStatus.RESOLVED,
        AlertStatus.FALSE_POSITIVE,
    },
    AlertStatus.IN_PROGRESS: {
        AlertStatus.RESOLVED,
        AlertStatus.ACKNOWLEDGED,
    },
    AlertStatus.RESOLVED: set(),
    AlertStatus.FALSE_POSITIVE: set(),
}


def allowed_next_statuses(current: AlertStatus) -> set[AlertStatus]:
    return _VALID_TRANSITIONS.get(current, set())


def is_valid_transition(current: AlertStatus, target: AlertStatus) -> bool:
    """True iff `current -> target` is an allowed lifecycle transition.

    Self-loops (target == current) are NOT allowed — they would be a
    no-op state change.  The application service treats self-loops as
    a no-op (returning the unchanged alert) rather than rejecting them.
    """
    return target in _VALID_TRANSITIONS.get(current, set())


# ─── Embedded view types ───────────────────────────────────


@dataclass
class AlertDeviation:
    """An embedded view of a top behavioral deviation for an alert.

    Mirrors `anomaly.BehavioralDeviation` but is owned by the alerts
    module so changes to the anomaly module don't break the alert
    contract.
    """

    feature: str
    value: float
    baseline_mean: float
    baseline_std: float
    zscore: float


@dataclass
class AlertFinding:
    """A detector finding cited by an insider-risk alert."""

    category: str
    title: str
    severity: float
    description: str
    detector: str
    day: datetime


# ─── Alert entity ──────────────────────────────────────────


@dataclass
class Alert:
    """
    A security alert produced from a Phase-5 anomaly result.

    `idempotency_key` is the unique, deterministic identifier used for
    de-duplication.  It is `(user_id, window, window_start_iso,
    model_version)`-derived and is also persisted as a unique
    index in MongoDB, so re-running detection or restarting the
    server does not create duplicate alerts.
    """

    # ─── Provenance ─────────────────────────────────────────
    idempotency_key: str
    # The ML result behind a behavioral-model alert; None for alerts raised
    # by the insider risk engine, which cite their findings instead.
    anomaly_result_id: uuid.UUID | None
    user_id: str
    source_dataset: str
    window: str
    window_start: datetime
    window_end: datetime
    model_version: str
    feature_version: str

    # ─── Content ────────────────────────────────────────────
    title: str
    description: str
    risk_score: float
    risk_level: str            # raw string from the anomaly result
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.OPEN
    top_behavioral_deviations: list[AlertDeviation] = field(default_factory=list)

    # ─── Workflow ───────────────────────────────────────────
    assigned_to: str | None = None  # user_id of the assignee
    investigation_id: uuid.UUID | None = None

    # ─── Insider risk context ───────────────────────────────
    #: "behavioral_model" (one ML result) or "insider_risk" (the risk engine).
    source: str = "behavioral_model"
    categories: list[str] = field(default_factory=list)
    findings: list[AlertFinding] = field(default_factory=list)
    employee_risk_score: float | None = None
    priority: float | None = None
    risk_components: dict[str, float] = field(default_factory=dict)

    # ─── Lifecycle ──────────────────────────────────────────
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    # First time an analyst acted on the alert (left OPEN), and when it was
    # closed out (RESOLVED or FALSE_POSITIVE). Response-time metrics use these.
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    # ─── Behaviour ──────────────────────────────────────────
    def change_status(self, target: AlertStatus) -> None:
        """Move the alert to `target`, raising if the transition is illegal.

        Allowed transitions are defined in `_VALID_TRANSITIONS`.  Self-loops
        are silently ignored (the alert remains in its current state and
        `updated_at` is not bumped) — this keeps API clients that retry
        the same call idempotent.
        """
        if target == self.status:
            return
        if not is_valid_transition(self.status, target):
            raise ValueError(
                f"Illegal alert status transition: {self.status.value} -> {target.value}"
            )
        now = _utcnow()
        self.status = target
        self.updated_at = now
        if self.acknowledged_at is None:
            self.acknowledged_at = now
        if target in (AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE):  # both terminal
            self.resolved_at = now

    def assign(self, user_id: str) -> None:
        self.assigned_to = user_id
        self.updated_at = _utcnow()

    def link_investigation(self, investigation_id: uuid.UUID) -> None:
        self.investigation_id = investigation_id
        self.updated_at = _utcnow()

    def unlink_investigation(self) -> None:
        """Clear the alert's link to any investigation.  Idempotent."""
        self.investigation_id = None
        self.updated_at = _utcnow()
