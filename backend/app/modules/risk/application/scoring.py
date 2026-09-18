"""
ITBIS — Risk Module: scoring

Turns a person's signals into their insider risk score for a day.

Component score
    Signals fade with age (half-life `half_life_days`; past incidents fade
    over `historical_half_life_days`) and combine as independent evidence:

        component = 100 * (1 - Π (1 - severity_i / 100))

    One strong signal dominates, several weaker ones add up, and the result
    never exceeds 100.

Insider risk score
    The weighted sum of the five components (weights in RISK_WEIGHTS).

Threat prioritisation
    A weighted sum is deliberately conservative: a single critical signal in
    one component moves the score only by that component's weight. So the
    queue is ordered by `priority`, the higher of the score and 0.8 x the
    day's live strength, so one serious event is never buried behind people
    with many mild ones. Today's signals combine with each other, because a
    quiet data theft shows up as several medium signals on one day rather
    than one loud one; older signals are weighed one at a time, so a run of
    mild days never adds up into an alert by itself.

Trend
    Today's score minus the average of the previous seven days' scores.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.modules.anomaly.application.risk_scoring import classify_risk_level
from app.modules.detection.domain.finding import Finding, day_start
from app.modules.risk.domain.model import (
    CATEGORY_COMPONENT,
    COMPONENT_LABELS,
    RISK_WEIGHTS,
    EmployeeRiskScore,
    RiskComponent,
    RiskSignal,
)


@dataclass(frozen=True)
class RiskSettings:
    weights: dict[RiskComponent, float] = field(default_factory=lambda: dict(RISK_WEIGHTS))
    half_life_days: float = 7.0
    lookback_days: int = 30
    historical_half_life_days: float = 90.0
    historical_lookback_days: int = 365
    priority_signal_factor: float = 0.8
    top_signals: int = 5


def decayed(severity: float, age_days: float, half_life_days: float) -> float:
    return severity * 0.5 ** (age_days / half_life_days)


def combine(severities: Iterable[float]) -> float:
    remaining = 1.0
    for s in severities:
        remaining *= 1.0 - max(0.0, min(100.0, s)) / 100.0
    return 100.0 * (1.0 - remaining)


def signals_from_findings(findings: Iterable[Finding]) -> list[RiskSignal]:
    return [
        RiskSignal(
            day=f.day,
            component=CATEGORY_COMPONENT[f.category],
            severity=f.severity,
            label=f.title,
            category=f.category,
            reference=f.key,
        )
        for f in findings
    ]


def score_employee(
    user_id: str,
    day: datetime,
    signals: Sequence[RiskSignal],
    *,
    previous_scores: Sequence[float] = (),
    settings: RiskSettings | None = None,
) -> EmployeeRiskScore:
    settings = settings or RiskSettings()
    day = day_start(day)

    live: dict[RiskComponent, list[tuple[float, RiskSignal]]] = {c: [] for c in RiskComponent}
    today: list[float] = []
    for signal in signals:
        age = (day - day_start(signal.day)).days
        historical = signal.component == RiskComponent.HISTORICAL_SECURITY_EVENTS
        lookback = settings.historical_lookback_days if historical else settings.lookback_days
        if age < 0 or age > lookback:
            continue  # future signals never leak into the past
        half_life = settings.historical_half_life_days if historical else settings.half_life_days
        live[signal.component].append((decayed(signal.severity, age, half_life), signal))
        if age == 0 and not historical:
            today.append(signal.severity)

    components = {
        component: round(combine(weight for weight, _ in entries), 1)
        for component, entries in live.items()
    }
    score = round(sum(settings.weights[c] * v for c, v in components.items()), 1)

    ranked = sorted((entry for entries in live.values() for entry in entries), key=lambda e: -e[0])
    # Today's signals count together: a quiet theft shows up as several medium
    # signals on one day, not as one loud one. Older signals stay individual,
    # so a run of mild days does not add up into an alert on its own.
    strongest_live = max(
        (w for w, s in ranked if s.component != RiskComponent.HISTORICAL_SECURITY_EVENTS),
        default=0.0,
    )
    combined_live = max(strongest_live, combine(today))
    contributions = {c: settings.weights[c] * v for c, v in components.items()}
    dominant = max(contributions, key=contributions.get) if score > 0 else None
    recent = list(previous_scores)[-7:]

    return EmployeeRiskScore(
        user_id=user_id,
        day=day,
        score=score,
        level=classify_risk_level(score),
        components=components,
        top_signals=[
            {
                "label": s.label,
                "component": s.component.value,
                "component_label": COMPONENT_LABELS[s.component],
                "category": s.category.value if s.category else None,
                "severity": round(s.severity, 1),
                "current_weight": round(w, 1),
                "day": day_start(s.day).date().isoformat(),
                "reference": s.reference,
            }
            for w, s in ranked[: settings.top_signals]
        ],
        dominant_component=dominant,
        trend=round(score - statistics.fmean(recent), 1) if recent else None,
        priority=round(max(score, settings.priority_signal_factor * combined_live), 1),
    )
