"""
ITBIS — Activity Module: API Router

Exposes endpoints for ingesting CERT log files and querying job status / statistics.
All endpoints require authentication and the appropriate RBAC permission.
"""
# ruff: noqa: B008  # FastAPI's Depends() in defaults is the documented pattern
import uuid

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.activity.application.dtos import StartIngestionDTO
from app.modules.activity.application.services.ingestion_service import IngestionService
from app.modules.activity.domain.exceptions import (
    EmptyFileError,
    IngestionJobNotFoundError,
    UnsupportedLogTypeError,
)
from app.modules.activity.infrastructure.repositories import (
    SQLIngestionErrorRepository,
)
from app.modules.activity.presentation.dependencies import get_ingestion_service
from app.modules.activity.presentation.schemas import (
    IngestionErrorListResponse,
    IngestionErrorResponse,
    IngestionJobListResponse,
    IngestionJobResponse,
    IngestionStatsResponse,
    IngestionUploadResponse,
)
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def _job_to_response(dto) -> IngestionJobResponse:
    return IngestionJobResponse(**dto.model_dump())


# ─── Upload / Start Ingestion ────────────────────────────────

@router.post(
    "/upload",
    response_model=IngestionUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a CERT log CSV and start an ingestion job",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_CREATE))],
)
async def upload_dataset(
    file: UploadFile = File(..., description="CERT-format CSV file"),
    source_dataset: str = Query("cert", description="Logical dataset name"),
    current_user: User = Depends(require_active_user),
    service: IngestionService = Depends(get_ingestion_service),
):
    """
    Upload a CERT log CSV. The log type is auto-detected from the
    column signature. The job is processed synchronously in the
    request scope and returns when complete.
    """
    content = await file.read()
    filename = file.filename or "uploaded.csv"

    dto = StartIngestionDTO(
        filename=filename,
        source_dataset=source_dataset,
        initiated_by=str(current_user.id),
    )

    try:
        job = await service.start_ingestion(content=content, dto=dto)
    except EmptyFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except UnsupportedLogTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return IngestionUploadResponse(
        message=f"Ingestion completed with status '{job.status}'.",
        job=_job_to_response(job),
    )


# ─── Read / Query ────────────────────────────────────────────

@router.get(
    "/jobs",
    response_model=IngestionJobListResponse,
    status_code=status.HTTP_200_OK,
    summary="List recent ingestion jobs",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def list_jobs(
    limit: int = Query(20, ge=1, le=200),
    service: IngestionService = Depends(get_ingestion_service),
):
    jobs = await service.list_recent_jobs(limit=limit)
    responses = [_job_to_response(j) for j in jobs]
    return IngestionJobListResponse(jobs=responses, count=len(responses))


@router.get(
    "/jobs/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get an ingestion job's status",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def get_job_status(
    job_id: uuid.UUID,
    service: IngestionService = Depends(get_ingestion_service),
):
    try:
        job = await service.get_job(job_id)
    except IngestionJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _job_to_response(job)


@router.get(
    "/jobs/{job_id}/errors",
    response_model=IngestionErrorListResponse,
    status_code=status.HTTP_200_OK,
    summary="List ingestion errors for a job",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def list_job_errors(
    job_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    repo = SQLIngestionErrorRepository(db)
    errors = await repo.list_for_job(job_id=job_id, limit=limit)
    return IngestionErrorListResponse(
        job_id=str(job_id),
        errors=[
            IngestionErrorResponse(
                id=str(e.id),
                job_id=str(e.job_id),
                row_number=e.row_number,
                reason=e.reason,
                raw_data=e.raw_data,
                occurred_at=e.occurred_at,
            )
            for e in errors
        ],
        count=len(errors),
    )


@router.get(
    "/stats",
    response_model=IngestionStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate ingestion statistics",
    dependencies=[Depends(require_permission(PermissionName.ALERTS_READ))],
)
async def get_ingestion_stats(
    service: IngestionService = Depends(get_ingestion_service),
):
    stats = await service.get_stats()
    return IngestionStatsResponse(**stats.model_dump())
