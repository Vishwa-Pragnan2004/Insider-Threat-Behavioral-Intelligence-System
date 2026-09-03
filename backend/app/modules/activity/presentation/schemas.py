"""
ITBIS — Activity Module: Pydantic API Schemas
"""
from datetime import datetime

from pydantic import BaseModel, Field

# ─── Requests ────────────────────────────────────────────────


class IngestionUploadResponse(BaseModel):
    """Returned by POST /ingestion/upload — wraps the job DTO with metadata."""

    message: str
    job: "IngestionJobResponse"


# ─── Responses ───────────────────────────────────────────────


class IngestionJobResponse(BaseModel):
    id: str
    filename: str
    log_type: str
    source_dataset: str
    status: str
    total_rows: int
    processed_rows: int
    failed_rows: int
    events_stored: int
    success_rate: float
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    error_message: str | None = None
    initiated_by: str | None = None

    model_config = {"from_attributes": True}


class IngestionJobListResponse(BaseModel):
    jobs: list[IngestionJobResponse] = Field(default_factory=list)
    count: int


class IngestionStatsResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    partial_jobs: int
    total_rows_processed: int
    total_events_stored: int
    total_errors: int
    jobs_by_log_type: dict[str, int] = Field(default_factory=dict)


class IngestionErrorResponse(BaseModel):
    id: str
    job_id: str
    row_number: int
    reason: str
    raw_data: dict | None = None
    occurred_at: datetime


class IngestionErrorListResponse(BaseModel):
    job_id: str
    errors: list[IngestionErrorResponse] = Field(default_factory=list)
    count: int


# Resolve forward reference
IngestionUploadResponse.model_rebuild()
