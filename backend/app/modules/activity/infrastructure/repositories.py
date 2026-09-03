"""
ITBIS — Activity Module: Concrete Repositories
SQLAlchemy implementations of activity repository interfaces.
"""
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.activity.domain.entities import IngestionError, IngestionJob
from app.modules.activity.domain.enums import JobStatus, LogType
from app.modules.activity.domain.repositories import (
    IIngestionErrorRepository,
    IIngestionJobRepository,
)
from app.modules.activity.infrastructure.models import (
    IngestionErrorModel,
    IngestionJobModel,
)


class SQLIngestionJobRepository(IIngestionJobRepository):
    """SQLAlchemy implementation of IIngestionJobRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_domain(self, m: IngestionJobModel) -> IngestionJob:
        return IngestionJob(
            id=m.id,
            filename=m.filename,
            log_type=m.log_type,
            source_dataset=m.source_dataset,
            status=m.status,
            total_rows=m.total_rows,
            processed_rows=m.processed_rows,
            failed_rows=m.failed_rows,
            events_stored=m.events_stored,
            started_at=m.started_at,
            completed_at=m.completed_at,
            created_at=m.created_at,
            updated_at=m.updated_at,
            error_message=m.error_message,
            initiated_by=m.initiated_by,
        )

    def _to_model(self, e: IngestionJob, m: IngestionJobModel | None) -> IngestionJobModel:
        model = m or IngestionJobModel(id=e.id)
        model.filename = e.filename
        model.log_type = e.log_type
        model.source_dataset = e.source_dataset
        model.status = e.status
        model.total_rows = e.total_rows
        model.processed_rows = e.processed_rows
        model.failed_rows = e.failed_rows
        model.events_stored = e.events_stored
        model.started_at = e.started_at
        model.completed_at = e.completed_at
        model.created_at = e.created_at
        model.updated_at = e.updated_at
        model.error_message = e.error_message
        model.initiated_by = e.initiated_by
        return model

    async def save(self, job: IngestionJob) -> IngestionJob:
        stmt = select(IngestionJobModel).where(IngestionJobModel.id == job.id)
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        model = self._to_model(job, existing)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def get_by_id(self, job_id: uuid.UUID) -> IngestionJob | None:
        stmt = select(IngestionJobModel).where(IngestionJobModel.id == job_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def list_recent(self, limit: int = 20) -> Sequence[IngestionJob]:
        stmt = (
            select(IngestionJobModel)
            .order_by(IngestionJobModel.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def get_stats(self) -> dict:
        """Aggregate statistics across all jobs."""

        stmt = select(IngestionJobModel)
        result = await self.session.execute(stmt)
        jobs = result.scalars().all()

        total_jobs = len(jobs)
        completed_jobs = sum(1 for j in jobs if j.status == JobStatus.COMPLETED)
        failed_jobs = sum(1 for j in jobs if j.status == JobStatus.FAILED)
        partial_jobs = sum(1 for j in jobs if j.status == JobStatus.PARTIAL)
        total_rows_processed = sum(j.processed_rows for j in jobs)
        total_events_stored = sum(j.events_stored for j in jobs)
        total_errors = sum(j.failed_rows for j in jobs)

        jobs_by_log_type: dict[str, int] = {}
        for j in jobs:
            key = j.log_type.value if isinstance(j.log_type, LogType) else str(j.log_type)
            jobs_by_log_type[key] = jobs_by_log_type.get(key, 0) + 1

        return {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "partial_jobs": partial_jobs,
            "total_rows_processed": total_rows_processed,
            "total_events_stored": total_events_stored,
            "total_errors": total_errors,
            "jobs_by_log_type": jobs_by_log_type,
        }


class SQLIngestionErrorRepository(IIngestionErrorRepository):
    """SQLAlchemy implementation of IIngestionErrorRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_domain(self, m: IngestionErrorModel) -> IngestionError:
        return IngestionError(
            id=m.id,
            job_id=m.job_id,
            row_number=m.row_number,
            reason=m.reason,
            raw_data=m.raw_data,
            occurred_at=m.occurred_at,
        )

    async def bulk_save(self, errors: Sequence[IngestionError]) -> None:
        if not errors:
            return
        models = [
            IngestionErrorModel(
                id=e.id,
                job_id=e.job_id,
                row_number=e.row_number,
                reason=e.reason,
                raw_data=e.raw_data,
                occurred_at=e.occurred_at,
            )
            for e in errors
        ]
        self.session.add_all(models)
        await self.session.flush()

    async def list_for_job(
        self, job_id: uuid.UUID, limit: int = 100
    ) -> Sequence[IngestionError]:
        stmt = (
            select(IngestionErrorModel)
            .where(IngestionErrorModel.job_id == job_id)
            .order_by(IngestionErrorModel.row_number.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]
