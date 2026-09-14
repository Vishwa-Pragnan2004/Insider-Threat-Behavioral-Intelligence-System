"""
ITBIS — Alerts Module: insider-risk alerts

Raises one alert per person per day from the insider risk engine, explaining
which categories fired and why.

When to alert
    The day's threat priority (see risk scoring) reaches `min_priority`, and
    something actually happened that day: a finding or model result dated
    that day. A person whose priority is still elevated only because of last
    week's findings fading out isn't alerted again every day.

As evidence grows
    The pipeline re-scores today as new events arrive. If today's alert is
    still OPEN it is refreshed (severity, findings, scores); once an analyst
    has picked it up it is left as they found it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.modules.alerts.domain.entities import Alert, AlertFinding
from app.modules.alerts.domain.enums import RISK_LEVEL_TO_SEVERITY, AlertStatus
from app.modules.anomaly.application.risk_scoring import classify_risk_level
from app.modules.detection.domain.categories import CATEGORY_LABELS, AnomalyCategory
from app.modules.detection.domain.finding import DETECTOR_VERSION, Finding
from app.modules.risk.domain.model import RISK_MODEL_VERSION, EmployeeRiskScore

SOURCE = "insider_risk"


@dataclass(frozen=True)
class RiskAlertPolicy:
    min_priority: float = 60.0


def risk_alert_key(user_id: str, day_iso: str) -> str:
    return f"{user_id}|daily|{day_iso}|{RISK_MODEL_VERSION}"


def findings_on_day(score: EmployeeRiskScore, findings: list[Finding]) -> list[Finding]:
    """The person's findings dated the scored day, strongest first."""
    return sorted(
        (f for f in findings if f.user_id == score.user_id and f.day == score.day),
        key=lambda f: -f.severity,
    )


def model_anomaly_on_day(score: EmployeeRiskScore) -> bool:
    today = score.day.date().isoformat()
    return any(
        s.get("category") == AnomalyCategory.BEHAVIORAL_ANOMALY.value and s.get("day") == today
        for s in score.top_signals
    )


def alert_warranted(
    score: EmployeeRiskScore,
    *,
    findings_today: int,
    model_today: bool,
    policy: RiskAlertPolicy | None = None,
) -> bool:
    """The alerting rule, shared by the live pipeline and dataset evaluations."""
    policy = policy or RiskAlertPolicy()
    return score.priority >= policy.min_priority and (findings_today > 0 or model_today)


class RiskAlertService:
    def __init__(self, alert_repo, policy: RiskAlertPolicy | None = None) -> None:  # noqa: ANN001
        self._alerts = alert_repo
        self._policy = policy or RiskAlertPolicy()

    async def raise_for(
        self, score: EmployeeRiskScore, findings: list[Finding]
    ) -> tuple[Alert | None, bool]:
        """Returns (alert, created). (None, False) when no alert is warranted."""
        todays = findings_on_day(score, findings)
        model_today = model_anomaly_on_day(score)
        if not alert_warranted(
            score, findings_today=len(todays), model_today=model_today, policy=self._policy
        ):
            return None, False

        alert = self._build(score, todays, model_today)
        saved, created = await self._alerts.upsert(alert)
        if not created and saved.status == AlertStatus.OPEN and _differs(saved, alert):
            for name in (
                "title",
                "description",
                "risk_score",
                "risk_level",
                "severity",
                "categories",
                "findings",
                "employee_risk_score",
                "priority",
                "risk_components",
            ):
                setattr(saved, name, getattr(alert, name))
            await self._alerts.update_content(saved)
        return saved, created

    def _build(self, score: EmployeeRiskScore, todays: list[Finding], model_today: bool) -> Alert:
        level = classify_risk_level(score.priority)
        severity = RISK_LEVEL_TO_SEVERITY[level]
        categories = list(dict.fromkeys(f.category.value for f in todays))
        if model_today:
            categories.append(AnomalyCategory.BEHAVIORAL_ANOMALY.value)
        labels = [CATEGORY_LABELS[AnomalyCategory(c)] for c in categories]
        reasons = " ".join(f"{f.title}: {f.description}" for f in todays[:3])
        if model_today:
            reasons += " The behavioral model also rated the day as unusual for this person."
        return Alert(
            idempotency_key=risk_alert_key(score.user_id, score.day.date().isoformat()),
            anomaly_result_id=None,
            user_id=score.user_id,
            source_dataset="all",
            window="daily",
            window_start=score.day,
            window_end=score.day + timedelta(days=1),
            model_version=RISK_MODEL_VERSION,
            feature_version=DETECTOR_VERSION,
            title=f"{severity.value.title()} insider risk: {', '.join(labels[:3])}",
            description=(
                f"Insider risk score {score.score:.0f}/100, threat priority "
                f"{score.priority:.0f}/100. {reasons}"
            ).strip(),
            risk_score=score.priority,
            risk_level=level.value,
            severity=severity,
            source=SOURCE,
            categories=categories,
            findings=[
                AlertFinding(
                    category=f.category.value,
                    title=f.title,
                    severity=f.severity,
                    description=f.description,
                    detector=f.detector,
                    day=f.day,
                )
                for f in todays
            ],
            employee_risk_score=score.score,
            priority=score.priority,
            risk_components={c.value: v for c, v in score.components.items()},
        )


def _differs(saved: Alert, fresh: Alert) -> bool:
    return (
        saved.severity != fresh.severity
        or saved.priority != fresh.priority
        or [(f.detector, f.severity) for f in saved.findings]
        != [(f.detector, f.severity) for f in fresh.findings]
    )
