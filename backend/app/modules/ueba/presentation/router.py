"""
ITBIS — UEBA: continuous detection pipeline API

    GET  /api/v1/ueba/pipeline/status   schedule, last run and run counts
    POST /api/v1/ueba/pipeline/run      run the pipeline now
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.core.redis_client import get_redis
from app.modules.anomaly.application.model_service import ModelService
from app.modules.anomaly.presentation.dependencies import get_model_service
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import require_permission
from app.modules.ueba.application.detection_pipeline import (
    DetectionPipeline,
    PipelineBusyError,
    PipelineRunResult,
    pipeline_coordinator,
    stages_factory_for,
)

router = APIRouter()


class PipelineRunResponse(BaseModel):
    run_id: str
    trigger: str
    succeeded: bool
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    window_start: datetime
    window_end: datetime
    feature_rows: int
    users_with_features: int
    anomaly_results: int
    anomalies_flagged: int
    high_risk_results: int
    alerts_created: int
    baselines_built: int
    findings: int
    risk_scores: int
    high_priority_employees: int
    detection_skipped_reason: str | None
    error: str | None

    @classmethod
    def from_result(cls, result: PipelineRunResult) -> PipelineRunResponse:
        return cls(**{name: getattr(result, name) for name in cls.model_fields})


class PipelineStatusResponse(BaseModel):
    scheduler_enabled: bool
    interval_seconds: int | None
    lookback_days: int | None
    running: bool
    runs_completed: int
    runs_failed: int
    last_success_at: datetime | None
    next_run_at: datetime | None
    last_run: PipelineRunResponse | None


@router.get(
    "/pipeline/status",
    response_model=PipelineStatusResponse,
    summary="Continuous detection pipeline: schedule and last run",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_READ))],
)
async def get_pipeline_status() -> PipelineStatusResponse:
    current = pipeline_coordinator.status
    return PipelineStatusResponse(
        scheduler_enabled=current.scheduler_enabled,
        interval_seconds=current.interval_seconds,
        lookback_days=current.lookback_days,
        running=current.running,
        runs_completed=current.runs_completed,
        runs_failed=current.runs_failed,
        last_success_at=current.last_success_at,
        next_run_at=current.next_run_at,
        last_run=(
            PipelineRunResponse.from_result(current.last_run) if current.last_run else None
        ),
    )


@router.post(
    "/pipeline/run",
    response_model=PipelineRunResponse,
    summary="Run features -> anomaly detection -> alerts now",
    dependencies=[Depends(require_permission(PermissionName.ANOMALY_CREATE))],
)
async def run_pipeline_now(
    session: AsyncSession = Depends(get_db),
    mongo_db: Any = Depends(get_mongo_db),
    redis: Any = Depends(get_redis),
    model_service: ModelService = Depends(get_model_service),
) -> PipelineRunResponse:
    pipeline = DetectionPipeline(
        stages_factory_for(session, mongo_db, model_service),
        lookback_days=get_settings().PIPELINE_LOOKBACK_DAYS,
    )
    try:
        result = await pipeline_coordinator.run(pipeline, trigger="manual", redis=redis)
    except PipelineBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pipeline run is already in progress on another API instance.",
        )
    return PipelineRunResponse.from_result(result)
