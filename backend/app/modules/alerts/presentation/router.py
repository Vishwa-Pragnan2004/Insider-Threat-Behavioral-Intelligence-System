"""
ITBIS — Alerts Module: API Router

Endpoints (all under /api/v1/alerts):

  GET    /                     list alerts (paginated, filterable)
  GET    /{alert_id}           get a single alert
  POST   /{alert_id}/acknowledge   mark alert as acknowledged
  POST   /{alert_id}/assign        assign alert to a user
  POST   /{alert_id}/status        change alert status
  POST   /generate                manually trigger alert generation

Permission map (re-uses Phase 1 RBAC):
  alerts:read     -> GET  endpoints
  alerts:create   -> POST /generate
  alerts:update   -> POST /{id}/{acknowledge|assign|status}
"""
# ruff: noqa: B008
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.alerts.application.alert_generation_service import (
    AlertGenerationService,
)
from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.application.dtos import (
    AlertAssignRequest,
    AlertDeviationDTO,
    AlertGenerateRequest,
    AlertGenerateResponse,
    AlertListResponse,
    AlertResponse,
    AlertStatusUpdateRequest,
)
from app.modules.alerts.domain.entities import Alert
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.exceptions import (
    AlertNotFoundError,
    AssigneeNotFoundError,
    IllegalAlertStatusTransitionError,
)
from app.modules.alerts.presentation.dependencies import (
    get_alert_generation_service,
    get_alert_service,
)
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)

log = structlog.get_logger(__name__)

router = APIRouter()


# ─── DTO helpers ───────────────────────────────────────────


def _to_response(a: Alert) -> AlertResponse:
    return AlertResponse(
        id=str(a.id),
        idempotency_key=a.idempotency_key,
        anomaly_result_id=str(a.anomaly_result_id),
        user_id=a.user_id,
        source_dataset=a.source_dataset,
        window=a.window,
        window_start=a.window_start,
        window_end=a.window_end,
        model_version=a.model_version,
        feature_version=a.feature_version,
        title=a.title,
        description=a.description,
        risk_score=a.risk_score,
        risk_level=a.risk_level,
        severity=a.severity.value,
        status=a.status.value,
        assigned_to=a.assigned_to,
        investigation_id=str(a.investigation_id) if a.investigation_id else None,
        top_behavioral_deviations=[
            AlertDeviationDTO(
                feature=d.feature,
                value=d.value,
                baseline_mean=d.baseline_mean,
                baseline_std=d.baseline_std,
                zscore=d.zscore,
            )
            for d in a.top_behavioral_deviations
        ],
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


# ─── Endpoints ────────────────────────────────────────────


@router.get(
    "/",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List alerts with optional filters and pagination",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def list_alerts(
    status_filter: AlertStatus | None = Query(None, alias="status"),
    severity: AlertSeverity | None = Query(None),
    user_id: str | None = Query(None),
    assigned_to: str | None = Query(None),
    risk_level: str | None = Query(None),
    source_dataset: str | None = Query(None),
    investigation_id: uuid.UUID | None = Query(None),
    start: str | None = Query(
        None,
        description="ISO-8601 UTC.  Filters by created_at >= start.",
    ),
    end: str | None = Query(
        None,
        description="ISO-8601 UTC.  Filters by created_at < end.",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    service: AlertService = Depends(get_alert_service),
):
    from datetime import datetime as _dt

    s = _dt.fromisoformat(start.replace("Z", "+00:00")) if start else None
    e = _dt.fromisoformat(end.replace("Z", "+00:00")) if end else None
    items, total = await service.list(
        status=status_filter,
        severity=severity,
        user_id=user_id,
        assigned_to=assigned_to,
        risk_level=risk_level,
        source_dataset=source_dataset,
        investigation_id=investigation_id,
        start=s,
        end=e,
        skip=skip,
        limit=limit,
    )
    return AlertListResponse(
        alerts=[_to_response(a) for a in items],
        count=len(items),
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single alert by id",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def get_alert(
    alert_id: uuid.UUID,
    service: AlertService = Depends(get_alert_service),
):
    try:
        return _to_response(await service.get(alert_id))
    except AlertNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark an alert as acknowledged",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_UPDATE))],
)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    service: AlertService = Depends(get_alert_service),
):
    try:
        return _to_response(await service.acknowledge(alert_id))
    except AlertNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except IllegalAlertStatusTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post(
    "/{alert_id}/assign",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Assign an alert to a user",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_UPDATE))],
)
async def assign_alert(
    alert_id: uuid.UUID,
    body: AlertAssignRequest,
    service: AlertService = Depends(get_alert_service),
):
    try:
        return _to_response(await service.assign(alert_id, body.user_id))
    except AlertNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except AssigneeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/{alert_id}/status",
    response_model=AlertResponse,
    status_code=status.HTTP_200_OK,
    summary="Change alert status (validates lifecycle transitions)",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_UPDATE))],
)
async def change_alert_status(
    alert_id: uuid.UUID,
    body: AlertStatusUpdateRequest,
    service: AlertService = Depends(get_alert_service),
):
    try:
        new_status = AlertStatus(body.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown status: {body.status!r}",
        ) from exc
    try:
        return _to_response(await service.change_status(alert_id, new_status))
    except AlertNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except IllegalAlertStatusTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post(
    "/generate",
    response_model=AlertGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger alert generation from existing anomaly results",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_CREATE))],
)
async def generate_alerts(
    payload: AlertGenerateRequest,
    current_user: User = Depends(require_active_user),
    service: AlertGenerationService = Depends(get_alert_generation_service),
):
    return await service.generate_for_existing_anomalies(
        start=payload.start,
        end=payload.end,
        user_id=payload.user_id,
        risk_level=payload.risk_level,
        source_dataset=payload.source_dataset,
        limit=payload.limit,
    )
