"""
ITBIS — Activity Module: Application DTOs
"""
from datetime import datetime

from pydantic import BaseModel, Field


class StartIngestionDTO(BaseModel):
    """Input DTO for starting an ingestion job."""
    filename: str
    source_dataset: str = "cert"
    initiated_by: str | None = None   # User ID


class IngestionJobDTO(BaseModel):
    """Output DTO representing an ingestion job's current state."""
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
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    error_message: str | None = None
    initiated_by: str | None = None

    model_config = {"from_attributes": True}


class IngestionStatsDTO(BaseModel):
    """Aggregate statistics across all ingestion jobs."""
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    partial_jobs: int = 0
    total_rows_processed: int = 0
    total_events_stored: int = 0
    total_errors: int = 0
    jobs_by_log_type: dict[str, int] = Field(default_factory=dict)
