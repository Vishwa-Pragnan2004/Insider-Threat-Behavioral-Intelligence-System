"""
ITBIS — Anomaly Module: API Router

Endpoints (all under /api/v1/anomaly):
  POST  /detect          -> run anomaly detection
  GET   /results         -> list recent results (filter by risk_level)
  GET   /results/{id}    -> fetch a single result
  GET   /users/{id}      -> list a user's results
  GET   /model-info      -> metadata about the loaded model
"""
# ruff: noqa: B008
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.anomaly.application.anomaly_detection_service import (
    AnomalyDetectionService,
)
from app.modules.anomaly.application.dtos import (
    AnomalyDetectRequest,
    AnomalyDetectResponse,
    AnomalyResultListResponse,
    AnomalyResultResponse,
    BehavioralDeviationResponse,
    ModelInfoResponse,
)
from app.modules.anomaly.application.model_service import ModelService
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel
from app.modules.anomaly.domain.exceptions import (
    FeatureIncompatibilityError,
    ModelLoadError,
    ModelNotLoadedError,
    NoDataForDetectionError,
)
from app.modules.anomaly.domain.repositories import IAnomalyResultStore
from app.modules.anomaly.presentation.dependencies import (
    get_anomaly_detection_service,
    get_model_service,
    get_result_store,
)
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)

log = structlog.get_logger(__name__)

router = APIRouter()


# ─── Helpers ─────────────────────────────────────────────


def _to_response(r) -> AnomalyResultResponse:
    return AnomalyResultResponse(
        id=str(r.id),
        user_id=r.user_id,
        source_dataset=r.source_dataset,
        window=r.window,
        window_start=r.window_start,
        window_end=r.window_end,
        model_version=r.model_version,
        feature_version=r.feature_version,
        prediction=r.prediction.value,
        raw_anomaly_score=r.raw_anomaly_score,
        risk_score=r.risk_score,
        risk_level=r.risk_level.value,
        baseline_source=r.baseline_source,
        top_behavioral_deviations=[
            BehavioralDeviationResponse(
                feature=d.feature,
                value=d.value,
                baseline_mean=d.baseline_mean,
                baseline_std=d.baseline_std,
                zscore=d.zscore,
            )
            for d in r.top_behavioral_deviations
        ],
        created_at=r.created_at,
    )


# ─── Endpoints ────────────────────────────────────────────


@router.post(
    "/detect",
    response_model=AnomalyDetectResponse,
    status_code=status.HTTP_200_OK,
    summary="Run anomaly detection for one user (or all users) over a date range",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_CREATE))],
)
async def run_detection(
    payload: AnomalyDetectRequest,
    current_user: User = Depends(require_active_user),
    service: AnomalyDetectionService = Depends(get_anomaly_detection_service),
):
    """Trigger detection.

    - If `user_id` is set, runs detection for that user only.
    - If `user_id` is omitted, runs detection for every user with
      features in the requested window.
    """
    try:
        if payload.user_id:
            results = await service.detect_for_user(
                user_id=payload.user_id,
                start=payload.start,
                end=payload.end,
                source_dataset=payload.source_dataset,
                window=payload.window,
                persist=True,
            )
        else:
            results = await service.detect_for_window(
                start=payload.start,
                end=payload.end,
                source_dataset=payload.source_dataset,
                window=payload.window,
                persist=True,
            )
    except NoDataForDetectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except (ModelLoadError, FeatureIncompatibilityError, ModelNotLoadedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model error: {exc}",
        ) from exc

    responses = [_to_response(r) for r in results]
    risk_levels: dict[str, int] = {}
    for r in responses:
        risk_levels[r.risk_level] = risk_levels.get(r.risk_level, 0) + 1
    return AnomalyDetectResponse(
        results=responses,
        count=len(responses),
        risk_levels=risk_levels,
    )


@router.get(
    "/results",
    response_model=AnomalyResultListResponse,
    status_code=status.HTTP_200_OK,
    summary="List recent anomaly results (optionally filtered by risk level)",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_READ))],
)
async def list_results(
    risk_level: RiskLevel | None = Query(None),
    prediction: AnomalyPrediction | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    store: IAnomalyResultStore = Depends(get_result_store),
):
    results = await store.list_recent(
        risk_level=risk_level,
        prediction=prediction,
        limit=limit,
    )
    return AnomalyResultListResponse(
        results=[_to_response(r) for r in results],
        count=len(results),
    )


@router.get(
    "/results/{result_id}",
    response_model=AnomalyResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single anomaly result by id",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_READ))],
)
async def get_result(
    result_id: uuid.UUID,
    store: IAnomalyResultStore = Depends(get_result_store),
):
    result = await store.get_by_id(result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly result {result_id} not found",
        )
    return _to_response(result)


@router.get(
    "/users/{user_id}/results",
    response_model=AnomalyResultListResponse,
    status_code=status.HTTP_200_OK,
    summary="List anomaly results for a specific user",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_READ))],
)
async def list_user_results(
    user_id: str,
    start: str | None = Query(None, description="ISO-8601 UTC"),
    end: str | None = Query(None, description="ISO-8601 UTC"),
    risk_level: RiskLevel | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    store: IAnomalyResultStore = Depends(get_result_store),
):
    from datetime import datetime as _dt

    s = _dt.fromisoformat(start.replace("Z", "+00:00")) if start else None
    e = _dt.fromisoformat(end.replace("Z", "+00:00")) if end else None
    results = await store.list_for_user(
        user_id=user_id,
        start=s,
        end=e,
        risk_level=risk_level,
        limit=limit,
    )
    return AnomalyResultListResponse(
        results=[_to_response(r) for r in results],
        count=len(results),
    )


@router.get(
    "/model-info",
    response_model=ModelInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Metadata about the loaded anomaly model artifact",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_READ))],
)
async def get_model_info(
    model_service: ModelService = Depends(get_model_service),
):
    art = model_service.get_artifact()
    try:
        model_service.validate_against_phase4()
        compatible = True
    except FeatureIncompatibilityError:
        compatible = False
    return ModelInfoResponse(
        artifact_path=art.path,
        model_version=art.model_version,
        feature_version=art.feature_version,
        feature_columns=art.feature_columns,
        z_feature_columns=art.z_feature_columns,
        model_features=art.model_features,
        n_features=len(art.model_features),
        score_low=art.score_low,
        score_high=art.score_high,
        phase4_feature_compatible=compatible,
    )
