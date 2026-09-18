"""
ITBIS — Analyst feedback API

    POST /api/v1/feedback/alerts/{alert_id}/verdict   judge an alert     alerts:update
    GET  /api/v1/feedback/alerts/{alert_id}/verdict   current + history  alerts:read
    GET  /api/v1/feedback/verdicts                    recent verdicts    alerts:read
    GET  /api/v1/feedback/stats                       measured precision alerts:read
    GET  /api/v1/feedback/labels                      training rows      alerts:read
"""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.modules.alerts.application.dtos import AlertResponse
from app.modules.alerts.domain.exceptions import AlertNotFoundError
from app.modules.alerts.presentation.router import _to_response as alert_to_response
from app.modules.feedback.application.verdict_service import (
    EmptyRationaleError,
    VerdictService,
)
from app.modules.feedback.domain.entities import AnalystVerdict
from app.modules.feedback.domain.enums import Verdict
from app.modules.feedback.presentation.dependencies import get_verdict_service
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)

log = structlog.get_logger(__name__)

router = APIRouter()


# ─── DTOs ──────────────────────────────────────────────────


class VerdictRequest(BaseModel):
    verdict: Verdict
    rationale: str = Field(
        ...,
        min_length=3,
        max_length=4000,
        description="Why this call was made. Required — an unexplained label cannot be audited.",
    )


class EvidenceResponse(BaseModel):
    source: str
    severity: str
    risk_score: float | None
    priority: float | None
    model_version: str
    feature_version: str
    detectors: list[str]
    categories: list[str]


class VerdictResponse(BaseModel):
    id: uuid.UUID
    alert_id: uuid.UUID
    subject_user_id: str
    subject_day: date
    verdict: Verdict
    rationale: str
    decided_by: str
    decided_at: str
    is_current: bool
    training_label: bool | None
    evidence: EvidenceResponse


class VerdictRecordedResponse(BaseModel):
    verdict: VerdictResponse
    alert: AlertResponse


class AlertVerdictResponse(BaseModel):
    current: VerdictResponse | None
    history: list[VerdictResponse]


class VerdictListResponse(BaseModel):
    items: list[VerdictResponse]
    total: int


class StatsResponse(BaseModel):
    total: int
    counts: dict[str, int]
    precision: float | None = Field(
        None,
        description=(
            "Share of decisively judged alerts that were real threats. "
            "None until at least one alert has been called either way."
        ),
    )
    trainable: int
    threats: int
    benign: int


class LabelResponse(BaseModel):
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


def _to_response(v: AnalystVerdict) -> VerdictResponse:
    return VerdictResponse(
        id=v.id,
        alert_id=v.alert_id,
        subject_user_id=v.subject_user_id,
        subject_day=v.subject_day,
        verdict=v.verdict,
        rationale=v.rationale,
        decided_by=v.decided_by,
        decided_at=v.decided_at.isoformat(),
        is_current=v.is_current,
        training_label=v.training_label,
        evidence=EvidenceResponse(
            source=v.evidence.source,
            severity=v.evidence.severity,
            risk_score=v.evidence.risk_score,
            priority=v.evidence.priority,
            model_version=v.evidence.model_version,
            feature_version=v.evidence.feature_version,
            detectors=list(v.evidence.detectors),
            categories=list(v.evidence.categories),
        ),
    )


# ─── Endpoints ─────────────────────────────────────────────


@router.post(
    "/alerts/{alert_id}/verdict",
    response_model=VerdictRecordedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record what an alert turned out to be",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_UPDATE))],
)
async def record_verdict(
    alert_id: uuid.UUID,
    body: VerdictRequest,
    current_user: User = Depends(require_active_user),
    service: VerdictService = Depends(get_verdict_service),
):
    """Judge an alert, and close it to match.

    Recording a second verdict on the same alert supersedes the first;
    both are kept. If the alert is already closed, the verdict is still
    recorded and the alert's status is left alone.
    """
    try:
        verdict, alert = await service.record(
            alert_id,
            verdict=body.verdict,
            rationale=body.rationale,
            decided_by=current_user.username,
        )
    except AlertNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except EmptyRationaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return VerdictRecordedResponse(
        verdict=_to_response(verdict), alert=alert_to_response(alert)
    )


@router.get(
    "/alerts/{alert_id}/verdict",
    response_model=AlertVerdictResponse,
    summary="The verdict in force on an alert, and every earlier one",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def get_alert_verdict(
    alert_id: uuid.UUID,
    service: VerdictService = Depends(get_verdict_service),
):
    history = await service.history_for_alert(alert_id)
    current = next((v for v in history if v.is_current), None)
    return AlertVerdictResponse(
        current=_to_response(current) if current else None,
        history=[_to_response(v) for v in history],
    )


@router.get(
    "/verdicts",
    response_model=VerdictListResponse,
    summary="Recently judged alerts",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def list_verdicts(
    since: date | None = Query(None, description="Earliest subject day to include"),
    until: date | None = Query(None, description="Latest subject day to include"),
    user_id: str | None = Query(None, description="Only verdicts about this person"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: VerdictService = Depends(get_verdict_service),
):
    items, total = await service.list_verdicts(
        since=since, until=until, subject_user_id=user_id, limit=limit, offset=offset
    )
    return VerdictListResponse(items=[_to_response(v) for v in items], total=total)


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="How often the system has been right, by analyst decision",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def verdict_stats(
    since: date | None = Query(None, description="Only count days from here on"),
    service: VerdictService = Depends(get_verdict_service),
):
    stats = await service.stats(since=since)
    return StatsResponse(
        total=stats.total,
        counts=stats.counts,
        precision=stats.precision,
        trainable=stats.trainable,
        threats=stats.threats,
        benign=stats.benign,
    )


@router.get(
    "/labels",
    response_model=list[LabelResponse],
    summary="Labelled days for supervised training",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def labelled_days(
    since: date | None = Query(None, description="Only days from here on"),
    service: VerdictService = Depends(get_verdict_service),
):
    """Confirmed threats and confirmed false positives, with the evidence
    the system had at the time.

    Policy violations and inconclusive calls are deliberately absent:
    neither is a clean example of either class, and guessing would teach
    a future model the wrong lesson.
    """
    rows = await service.labelled_dataset(since=since)
    return [LabelResponse(**row.__dict__) for row in rows]
