"""
ITBIS — Activity Module: Repository Interfaces
"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.modules.activity.domain.entities import IngestionError, IngestionJob


class IIngestionJobRepository(ABC):
    """Persistence interface for IngestionJob entities (PostgreSQL)."""

    @abstractmethod
    async def save(self, job: IngestionJob) -> IngestionJob:
        """Persist a new or updated job."""

    @abstractmethod
    async def get_by_id(self, job_id: uuid.UUID) -> IngestionJob | None:
        """Retrieve a job by its UUID."""

    @abstractmethod
    async def list_recent(self, limit: int = 20) -> Sequence[IngestionJob]:
        """Return the most recent jobs ordered by created_at desc."""

    @abstractmethod
    async def get_stats(self) -> dict:
        """Return aggregate statistics across all jobs."""


class IIngestionErrorRepository(ABC):
    """Persistence interface for IngestionError entities (PostgreSQL)."""

    @abstractmethod
    async def bulk_save(self, errors: Sequence[IngestionError]) -> None:
        """Persist a batch of ingestion errors."""

    @abstractmethod
    async def list_for_job(self, job_id: uuid.UUID, limit: int = 100) -> Sequence[IngestionError]:
        """Retrieve errors recorded for a specific job."""


class IActivityEventStore(ABC):
    """Storage interface for canonical activity events (MongoDB)."""

    @abstractmethod
    async def insert_many(
        self, events: Sequence[dict], job_id: str | None = None
    ) -> int:
        """Bulk-insert serialized canonical events. Returns count inserted."""

    @abstractmethod
    async def count_for_job(self, job_id: str) -> int:
        """Count events stored for a given ingestion job."""
