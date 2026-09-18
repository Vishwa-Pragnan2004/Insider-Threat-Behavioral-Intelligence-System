"""
ITBIS — Feedback Module: Verdict Service

Recording what an alert turned out to be, and turning those judgements
into two things:

  - a measurement of how often the system is right, against real analyst
    decisions rather than a benchmark dataset;
  - a labelled dataset, so that a supervised model can eventually be
    trained on this organisation's own confirmed cases.

Two decisions worth stating plainly, because both were tempting to get
wrong:

Labels are never inferred from workflow.
    Closing an alert as FALSE_POSITIVE looks like a free label, and
    harvesting those would multiply the dataset overnight. It would also
    poison it: analysts close alerts because they are duplicates, because
    another team owns them, or because the queue is long. A label has to
    be something a person asserted on purpose.

A verdict is recorded even when the alert's status cannot move.
    RESOLVED and FALSE_POSITIVE are terminal, so an analyst revising a
    months-old call would hit an illegal transition. The verdict is the
    record of truth; the status is a queue position. When they disagree,
    the verdict wins and the status is left where it is.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

import structlog

from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.domain.entities import Alert, allowed_next_statuses
from app.modules.alerts.domain.enums import AlertStatus
from app.modules.feedback.domain.entities import AnalystVerdict, EvidenceSnapshot
from app.modules.feedback.domain.enums import DECISIVE, TRAINING_LABEL, Verdict
from app.modules.feedback.domain.repositories import IVerdictRepository

log = structlog.get_logger(__name__)


class VerdictError(Exception):
    """Base class for verdict problems."""


class EmptyRationaleError(VerdictError):
    """A verdict was submitted without an explanation."""


#: Where a verdict leaves the alert in the queue. INCONCLUSIVE is absent
#: on purpose: "we looked and we still don't know" is not a closure, and
#: forcing one would hide work that is genuinely unfinished.
VERDICT_STATUS: dict[Verdict, AlertStatus] = {
    Verdict.CONFIRMED_THREAT: AlertStatus.RESOLVED,
    Verdict.POLICY_VIOLATION: AlertStatus.RESOLVED,
    Verdict.BENIGN: AlertStatus.FALSE_POSITIVE,
}

MIN_RATIONALE_CHARS = 3


@dataclass(frozen=True)
class VerdictStats:
    """How the system has been doing, judged by the people using it."""

    total: int
    counts: dict[str, int]
    #: Of the alerts an analyst called either way, the share that were real.
    precision: float | None
    #: Rows a supervised model could train on today.
    trainable: int
    threats: int
    benign: int


@dataclass(frozen=True)
class LabelledDay:
    """One training row: a person, a day, and whether it was a threat."""

    subject_user_id: str
    subject_day: date
    label: bool
    verdict: str
    priority: float | None
    risk_score: float | None
    detectors: list[str]
    categories: list[str]
    model_version: str
    feature_version: str
    decided_at: str


def snapshot_of(alert: Alert) -> EvidenceSnapshot:
    """What the system believed when it raised `alert`."""
    return EvidenceSnapshot(
        source=alert.source,
        severity=alert.severity.value,
        risk_score=alert.employee_risk_score if alert.employee_risk_score is not None
        else alert.risk_score,
        priority=alert.priority,
        model_version=alert.model_version,
        feature_version=alert.feature_version,
        detectors=sorted({f.detector for f in alert.findings}),
        categories=list(alert.categories),
    )


class VerdictService:
    def __init__(self, repo: IVerdictRepository, alerts: AlertService) -> None:
        self.repo = repo
        self.alerts = alerts

    # ─── Recording ───────────────────────────────────────

    async def record(
        self,
        alert_id: uuid.UUID,
        *,
        verdict: Verdict,
        rationale: str,
        decided_by: str,
    ) -> tuple[AnalystVerdict, Alert]:
        """Judge an alert. Supersedes any earlier verdict on the same alert.

        Raises AlertNotFoundError if the alert does not exist, and
        EmptyRationaleError if no explanation was given.
        """
        rationale = rationale.strip()
        if len(rationale) < MIN_RATIONALE_CHARS:
            raise EmptyRationaleError(
                "A verdict needs an explanation: an unexplained label cannot be audited later."
            )

        alert = await self.alerts.get(alert_id)

        entry = AnalystVerdict(
            alert_id=alert_id,
            subject_user_id=alert.user_id,
            subject_day=alert.window_start.date(),
            verdict=verdict,
            rationale=rationale,
            decided_by=decided_by,
            evidence=snapshot_of(alert),
        )
        # Retire the old verdict before inserting the new one: only one may be
        # in force per alert, and the database enforces it.
        previous = await self.repo.current_for_alert(alert_id)
        if previous is not None:
            previous.supersede(entry.id)
            await self.repo.update(previous)
        recorded = await self.repo.add(entry)

        alert = await self._move_status(alert, verdict)

        log.info(
            "feedback.verdict_recorded",
            alert_id=str(alert_id),
            verdict=verdict.value,
            subject=alert.user_id,
            decided_by=decided_by,
            revised=previous is not None,
            alert_status=alert.status.value,
        )
        return recorded, alert

    async def _move_status(self, alert: Alert, verdict: Verdict) -> Alert:
        """Close the alert to match the verdict, where the lifecycle allows it."""
        target = VERDICT_STATUS.get(verdict)
        if target is None or target == alert.status:
            return alert
        if target not in allowed_next_statuses(alert.status):
            # Terminal already, or an illegal move. The verdict still stands.
            log.info(
                "feedback.status_unchanged",
                alert_id=str(alert.id),
                status=alert.status.value,
                wanted=target.value,
            )
            return alert
        return await self.alerts.change_status(alert.id, target)

    # ─── Reading ─────────────────────────────────────────

    async def current_for_alert(self, alert_id: uuid.UUID) -> AnalystVerdict | None:
        return await self.repo.current_for_alert(alert_id)

    async def history_for_alert(self, alert_id: uuid.UUID) -> list[AnalystVerdict]:
        return await self.repo.history_for_alert(alert_id)

    async def list_verdicts(
        self,
        *,
        since: date | None = None,
        until: date | None = None,
        subject_user_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AnalystVerdict], int]:
        return await self.repo.list_current(
            since=since,
            until=until,
            subject_user_id=subject_user_id,
            limit=limit,
            offset=offset,
        )

    async def stats(self, *, since: date | None = None) -> VerdictStats:
        verdicts, _ = await self.repo.list_current(since=since, limit=100_000)
        counts = Counter(v.verdict for v in verdicts)
        threats = counts[Verdict.CONFIRMED_THREAT]
        benign = counts[Verdict.BENIGN]
        decisive = sum(counts[v] for v in DECISIVE)
        return VerdictStats(
            total=len(verdicts),
            counts={v.value: counts[v] for v in Verdict},
            precision=round(threats / decisive, 3) if decisive else None,
            trainable=sum(1 for v in verdicts if TRAINING_LABEL[v.verdict] is not None),
            threats=threats,
            benign=benign,
        )

    async def labelled_dataset(self, *, since: date | None = None) -> list[LabelledDay]:
        """Rows a supervised model can train on.

        Only decisive verdicts appear here. Policy violations and
        inconclusive calls are stored but withheld: see TRAINING_LABEL.
        """
        verdicts, _ = await self.repo.list_current(since=since, limit=100_000)
        rows: list[LabelledDay] = []
        for v in verdicts:
            label = v.training_label
            if label is None:
                continue
            rows.append(
                LabelledDay(
                    subject_user_id=v.subject_user_id,
                    subject_day=v.subject_day,
                    label=label,
                    verdict=v.verdict.value,
                    priority=v.evidence.priority,
                    risk_score=v.evidence.risk_score,
                    detectors=list(v.evidence.detectors),
                    categories=list(v.evidence.categories),
                    model_version=v.evidence.model_version,
                    feature_version=v.evidence.feature_version,
                    decided_at=v.decided_at.isoformat(),
                )
            )
        return rows
