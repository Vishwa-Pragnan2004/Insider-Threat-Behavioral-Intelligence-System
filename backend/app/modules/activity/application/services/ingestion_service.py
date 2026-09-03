"""
ITBIS — Activity Module: Ingestion Service

Orchestrates the full ingestion pipeline:
  CSV bytes -> log-type detection -> parser -> batched events/errors
  -> Postgres (job + errors) + MongoDB (canonical events)
"""
import uuid

import structlog

from app.modules.activity.application.dtos import (
    IngestionJobDTO,
    IngestionStatsDTO,
    StartIngestionDTO,
)
from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.application.parsers.registry import detect_parser
from app.modules.activity.application.services.batch_processor import BatchProcessor
from app.modules.activity.domain.entities import IngestionError, IngestionJob
from app.modules.activity.domain.enums import JobStatus, LogType
from app.modules.activity.domain.exceptions import (
    EmptyFileError,
    IngestionJobNotFoundError,
    UnsupportedLogTypeError,
)
from app.modules.activity.domain.repositories import (
    IActivityEventStore,
    IIngestionErrorRepository,
    IIngestionJobRepository,
)
from app.shared.schemas.canonical_event import CanonicalEvent

logger = structlog.get_logger(__name__)


class IngestionService:
    """
    Application service that drives dataset ingestion.

    Responsibilities:
      - Detect the parser for an uploaded CSV
      - Persist an IngestionJob (PENDING) and process it (RUNNING -> COMPLETED/PARTIAL/FAILED)
      - Stream events to MongoDB and errors to Postgres
      - Provide query helpers for status and aggregate statistics
    """

    def __init__(
        self,
        job_repo: IIngestionJobRepository,
        error_repo: IIngestionErrorRepository,
        event_store: IActivityEventStore,
        chunk_size: int = 500,
    ) -> None:
        self.job_repo = job_repo
        self.error_repo = error_repo
        self.event_store = event_store
        self.chunk_size = chunk_size

    # ─── Public API ───────────────────────────────────────────

    async def start_ingestion(
        self,
        content: bytes,
        dto: StartIngestionDTO,
    ) -> IngestionJobDTO:
        """Start a new ingestion job from raw CSV bytes."""
        if not content or not content.strip():
            raise EmptyFileError("Uploaded file is empty.")

        # 1. Detect log type from header
        processor = BatchProcessor(parser=None, chunk_size=self.chunk_size)  # type: ignore[arg-type]
        columns = processor.read_columns(content)
        parser: BaseParser = detect_parser(columns)

        # 2. Create job entity
        job = IngestionJob(
            id=uuid.uuid4(),
            filename=dto.filename,
            log_type=parser.LOG_TYPE,
            source_dataset=parser.SOURCE_DATASET,
            status=JobStatus.PENDING,
            total_rows=processor.count_rows(content),
            initiated_by=dto.initiated_by,
        )
        await self.job_repo.save(job)

        # 3. Process
        try:
            await self._run_job(job, content, parser)
        except UnsupportedLogTypeError:
            job.mark_failed("Unsupported log type")
            await self.job_repo.save(job)
            raise
        except Exception as exc:  # catastrophic failure
            logger.exception("ingestion_job_failed", job_id=str(job.id), error=str(exc))
            job.mark_failed(str(exc))
            await self.job_repo.save(job)
            raise

        # 4. Return final state
        final = await self.job_repo.get_by_id(job.id)
        return self._to_dto(final or job)

    async def get_job(self, job_id: uuid.UUID) -> IngestionJobDTO:
        job = await self.job_repo.get_by_id(job_id)
        if job is None:
            raise IngestionJobNotFoundError(f"Ingestion job {job_id} not found")
        return self._to_dto(job)

    async def list_recent_jobs(self, limit: int = 20) -> list[IngestionJobDTO]:
        jobs = await self.job_repo.list_recent(limit=limit)
        return [self._to_dto(j) for j in jobs]

    async def get_stats(self) -> IngestionStatsDTO:
        stats = await self.job_repo.get_stats()
        return IngestionStatsDTO(
            total_jobs=stats.get("total_jobs", 0),
            completed_jobs=stats.get("completed_jobs", 0),
            failed_jobs=stats.get("failed_jobs", 0),
            partial_jobs=stats.get("partial_jobs", 0),
            total_rows_processed=stats.get("total_rows_processed", 0),
            total_events_stored=stats.get("total_events_stored", 0),
            total_errors=stats.get("total_errors", 0),
            jobs_by_log_type=stats.get("jobs_by_log_type", {}),
        )

    # ─── Internals ────────────────────────────────────────────

    async def _run_job(
        self,
        job: IngestionJob,
        content: bytes,
        parser: BaseParser,
    ) -> None:
        """Execute the per-chunk ingestion flow."""
        job.mark_running()
        await self.job_repo.save(job)

        processor = BatchProcessor(parser=parser, chunk_size=self.chunk_size)
        job_id_str = str(job.id)

        total_events = 0
        total_errors = 0
        error_buffer: list[IngestionError] = []

        for chunk in processor.iter_chunks(content=content, job_id=job_id_str):
            # processed_rows counts every row touched (good + bad)
            chunk_total = len(chunk.events) + len(chunk.errors)
            if chunk_total:
                job.increment_processed(chunk_total)

            # Persist events
            if chunk.events:
                serialized = [self._serialise_event(e, job_id_str) for e in chunk.events]
                inserted = await self.event_store.insert_many(serialized, job_id=job_id_str)
                total_events += inserted
                job.increment_stored(inserted)

            # Persist errors
            if chunk.errors:
                total_errors += len(chunk.errors)
                job.increment_failed(len(chunk.errors))
                error_buffer.extend(chunk.errors)

            # Flush errors in batches to avoid huge transactions
            if len(error_buffer) >= self.chunk_size:
                await self.error_repo.bulk_save(error_buffer)
                error_buffer = []

            # Persist updated job counters
            await self.job_repo.save(job)

        # Flush remaining errors
        if error_buffer:
            await self.error_repo.bulk_save(error_buffer)

        job.mark_completed()
        await self.job_repo.save(job)

    @staticmethod
    def _serialise_event(event: CanonicalEvent, job_id: str) -> dict:
        """Serialise a CanonicalEvent to a plain dict for Mongo storage."""
        doc = event.model_dump(mode="json")
        doc["job_id"] = job_id
        return doc

    @staticmethod
    def _to_dto(job: IngestionJob) -> IngestionJobDTO:
        return IngestionJobDTO(
            id=str(job.id),
            filename=job.filename,
            log_type=job.log_type.value
            if isinstance(job.log_type, LogType)
            else str(job.log_type),
            source_dataset=job.source_dataset,
            status=job.status.value
            if hasattr(job.status, "value")
            else str(job.status),
            total_rows=job.total_rows,
            processed_rows=job.processed_rows,
            failed_rows=job.failed_rows,
            events_stored=job.events_stored,
            success_rate=job.success_rate,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            error_message=job.error_message,
            initiated_by=job.initiated_by,
        )
