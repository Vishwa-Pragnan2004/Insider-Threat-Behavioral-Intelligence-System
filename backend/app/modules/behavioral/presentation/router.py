"""
ITBIS — Behavioral Module: API Router

Endpoints (all under /api/v1/behavioral):
  POST /generate          -> trigger a feature generation run
  GET  /features          -> list feature rows (optionally filtered)
  GET  /profile/{user_id} -> fetch a user's baseline
"""
# ruff: noqa: B008  # FastAPI Depends() in defaults is the documented pattern
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.modules.behavioral.application.dtos import (
    BehavioralFeatureListResponse,
    BehavioralFeatureRow,
    BehavioralProfileResponse,
    FeatureGenerationRequest,
    FeatureGenerationResponse,
    TrainingExportRequest,
    TrainingExportResponse,
)
from app.modules.behavioral.application.services.feature_engineering_service import (
    FeatureEngineeringService,
)
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.exceptions import NoDataForBaselineError
from app.modules.behavioral.presentation.dependencies import (
    get_feature_engineering_service,
)
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)

log = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/generate",
    response_model=FeatureGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate behavioral features for events in [start, end)",
    dependencies=[Depends(require_permission(PermissionName.BEHAVIORAL_CREATE))],
)
async def generate_features(
    payload: FeatureGenerationRequest,
    current_user: User = Depends(require_active_user),
    service: FeatureEngineeringService = Depends(get_feature_engineering_service),
):
    rows = await service.generate_features(
        start=payload.start,
        end=payload.end,
        source_dataset=payload.source_dataset,
        user_ids=payload.user_ids,
        window=payload.window,
    )
    users = sorted({r.user_id for r in rows})
    return FeatureGenerationResponse(
        rows_generated=len(rows),
        users_processed=len(users),
        feature_version=FEATURE_VERSION,
        start=payload.start,
        end=payload.end,
        source_dataset=payload.source_dataset,
        window=payload.window,
    )


@router.get(
    "/features",
    response_model=BehavioralFeatureListResponse,
    status_code=status.HTTP_200_OK,
    summary="List computed feature rows for a user",
    dependencies=[Depends(require_permission(PermissionName.BEHAVIORAL_READ))],
)
async def list_features(
    user_id: str = Query(..., min_length=1),
    start: datetime | None = None,
    end: datetime | None = None,
    source_dataset: str | None = Query(None, max_length=64),
    service: FeatureEngineeringService = Depends(get_feature_engineering_service),
):
    rows = await service.list_features_for_user(
        user_id=user_id,
        start=start,
        end=end,
        source_dataset=source_dataset,
    )
    return BehavioralFeatureListResponse(
        user_id=user_id,
        rows=[
            BehavioralFeatureRow(
                id=str(r.id),
                user_id=r.user_id,
                window=r.window,
                window_start=r.window_start,
                window_end=r.window_end,
                source_dataset=r.source_dataset,
                feature_version=r.feature_version,
                event_count=r.event_count,
                features=dict(r.features),
            )
            for r in rows
        ],
        count=len(rows),
        feature_version=FEATURE_VERSION,
    )


@router.get(
    "/profile/{user_id}",
    response_model=BehavioralProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Fetch a user's behavioral baseline profile",
    dependencies=[Depends(require_permission(PermissionName.BEHAVIORAL_READ))],
)
async def get_profile(
    user_id: str,
    service: FeatureEngineeringService = Depends(get_feature_engineering_service),
):
    try:
        baseline = await service.build_baseline(
            user_id=user_id,
            # We use a 30-day trailing window by default.  In Phase 5+ this
            # becomes a real configuration option driven by the user
            # profile and the evaluation context.
            history_start=datetime.utcnow().replace(microsecond=0)
            - __import__("datetime").timedelta(days=30),
            history_end=datetime.utcnow().replace(microsecond=0),
        )
    except NoDataForBaselineError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No baseline data available for user {user_id!r}",
        ) from exc
    return BehavioralProfileResponse(
        user_id=baseline.user_id,
        feature_version=baseline.feature_version,
        observation_days=baseline.observation_days,
        window_start=baseline.window_start,
        window_end=baseline.window_end,
        source_dataset=baseline.source_dataset,
        stats=baseline.stats,
        updated_at=baseline.updated_at,
    )


# ─── Phase 5: Training dataset export ─────────────────────


@router.post(
    "/export",
    response_model=TrainingExportResponse,
    status_code=status.HTTP_200_OK,
    summary=(
        "Export a version-locked training dataset for offline / Kaggle "
        "model training (Phase 5).  Produces features.csv + manifest.json."
    ),
    dependencies=[Depends(require_permission(PermissionName.BEHAVIORAL_READ))],
)
async def export_training_dataset(
    payload: TrainingExportRequest,
    current_user: User = Depends(require_active_user),
    service: FeatureEngineeringService = Depends(get_feature_engineering_service),
):
    """Trigger a training dataset export.

    The export is **synchronous** for Phase 5 because the dataset is
    small in development.  The endpoint produces two artefacts in
    `output_dir`:

      - `features.csv` — metadata columns followed by the locked
        `FEATURE_NAMES` columns, one row per `(user_id, window,
        window_start)`.  Rows are sorted for byte-stable output.
      - `manifest.json` — provenance, column order, feature schema, and
        the contract guarantees (version lock, leakage guards, missing-
        value policy).
    """
    result = await service.export_training_dataset(
        start=payload.start,
        end=payload.end,
        source_dataset=payload.source_dataset,
        window=payload.window,
        output_dir=payload.output_dir,
    )
    return TrainingExportResponse(
        row_count=result.row_count,
        user_count=result.user_count,
        window_count=result.window_count,
        feature_version=result.feature_version,
        start=result.start,
        end=result.end,
        source_dataset=result.source_dataset,
        window=result.window,
        manifest_path=result.manifest_path,
        features_csv_path=result.features_csv_path,
        column_order=result.column_order,
        warnings=result.warnings,
    )
