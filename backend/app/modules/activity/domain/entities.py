"""
ITBIS — Activity Module: Domain Entities

Core domain objects for the activity ingestion pipeline.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.modules.activity.domain.enums import JobStatus, LogType


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ─── Ingestion Job ───────────────────────────────────────────

@dataclass
class IngestionJob:
    """
    Represents a single dataset ingestion run.
    Tracks lifecycle, progress, and outcome statistics.
    """
    id: uuid.UUID
    filename: str
    log_type: LogType
    source_dataset: str            # e.g. "cert_r4.2"
    status: JobStatus = JobStatus.PENDING
    total_rows: int = 0
    processed_rows: int = 0
    failed_rows: int = 0
    events_stored: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    error_message: str | None = None     # Set only on fatal job failure
    initiated_by: str | None = None      # User ID who triggered upload

    # Derived / convenience
    @property
    def success_rate(self) -> float:
        if self.total_rows == 0:
            return 0.0
        return round((self.processed_rows - self.failed_rows) / self.total_rows * 100, 2)

    def mark_running(self) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = _utcnow()
        self.updated_at = _utcnow()

    def mark_completed(self) -> None:
        self.status = JobStatus.PARTIAL if self.failed_rows > 0 else JobStatus.COMPLETED
        self.completed_at = _utcnow()
        self.updated_at = _utcnow()

    def mark_failed(self, reason: str) -> None:
        self.status = JobStatus.FAILED
        self.error_message = reason
        self.completed_at = _utcnow()
        self.updated_at = _utcnow()

    def increment_processed(self, count: int = 1) -> None:
        self.processed_rows += count
        self.updated_at = _utcnow()

    def increment_failed(self, count: int = 1) -> None:
        self.failed_rows += count
        self.updated_at = _utcnow()

    def increment_stored(self, count: int = 1) -> None:
        self.events_stored += count
        self.updated_at = _utcnow()


# ─── Ingestion Error ─────────────────────────────────────────

@dataclass
class IngestionError:
    """Records a single failed row during ingestion."""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    job_id: uuid.UUID = field(default=None)
    row_number: int = 0
    reason: str = ""
    raw_data: dict[str, Any] | None = None
    occurred_at: datetime = field(default_factory=_utcnow)
