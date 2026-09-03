"""
ITBIS — Unit tests for IngestionService with in-memory fakes.

No Postgres / Mongo required — uses lightweight fake repos.
"""
import uuid
from collections.abc import Sequence

import pytest

from app.modules.activity.application.dtos import StartIngestionDTO
from app.modules.activity.application.services.ingestion_service import IngestionService
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

# ─── Fakes ──────────────────────────────────────────────────


class FakeJobRepo(IIngestionJobRepository):
    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, IngestionJob] = {}

    async def save(self, job: IngestionJob) -> IngestionJob:
        self.jobs[job.id] = job
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> IngestionJob | None:
        return self.jobs.get(job_id)

    async def list_recent(self, limit: int = 20) -> Sequence[IngestionJob]:
        return sorted(
            self.jobs.values(), key=lambda j: j.created_at, reverse=True
        )[:limit]

    async def get_stats(self) -> dict:
        all_jobs = list(self.jobs.values())
        jobs_by_log_type: dict[str, int] = {}
        for j in all_jobs:
            key = j.log_type.value if isinstance(j.log_type, LogType) else str(j.log_type)
            jobs_by_log_type[key] = jobs_by_log_type.get(key, 0) + 1
        return {
            "total_jobs": len(all_jobs),
            "completed_jobs": sum(1 for j in all_jobs if j.status == JobStatus.COMPLETED),
            "failed_jobs": sum(1 for j in all_jobs if j.status == JobStatus.FAILED),
            "partial_jobs": sum(1 for j in all_jobs if j.status == JobStatus.PARTIAL),
            "total_rows_processed": sum(j.processed_rows for j in all_jobs),
            "total_events_stored": sum(j.events_stored for j in all_jobs),
            "total_errors": sum(j.failed_rows for j in all_jobs),
            "jobs_by_log_type": jobs_by_log_type,
        }


class FakeErrorRepo(IIngestionErrorRepository):
    def __init__(self) -> None:
        self.errors: list[IngestionError] = []

    async def bulk_save(self, errors: Sequence[IngestionError]) -> None:
        self.errors.extend(errors)

    async def list_for_job(self, job_id, limit=100):
        return [e for e in self.errors if e.job_id == job_id][:limit]


class FakeEventStore(IActivityEventStore):
    def __init__(self) -> None:
        self.docs: list[dict] = []

    async def insert_many(self, events, job_id=None):
        for e in events:
            doc = e if isinstance(e, dict) else e.model_dump(mode="json")
            if job_id is not None:
                doc["job_id"] = job_id
            self.docs.append(doc)
        return len(events)

    async def count_for_job(self, job_id):
        return sum(1 for d in self.docs if d.get("job_id") == job_id)


@pytest.fixture
def service() -> IngestionService:
    return IngestionService(
        job_repo=FakeJobRepo(),
        error_repo=FakeErrorRepo(),
        event_store=FakeEventStore(),
        chunk_size=2,
    )


VALID_LOGON = (
    b"id,date,user,pc,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"
    b"2,01/02/2010 17:00:00,alice,PC1,Logoff\n"
    b"3,01/03/2010 08:00:00,bob,PC2,Logon\n"
)


MALFORMED_LOGON = (
    b"id,date,user,pc,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"
    b"2,NOTADATE,alice,PC1,Logoff\n"
    b"3,01/02/2010 08:05:00,,PC2,Logon\n"
)


# ─── start_ingestion ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_ingestion_happy_path(service: IngestionService):
    dto = StartIngestionDTO(filename="logon.csv", initiated_by="u1")
    job = await service.start_ingestion(content=VALID_LOGON, dto=dto)

    assert job.status in ("completed", "partial")
    assert job.log_type == "logon"
    assert job.total_rows == 3
    assert job.events_stored == 3
    assert job.processed_rows == 3
    assert job.failed_rows == 0
    assert job.started_at is not None
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_start_ingestion_with_malformed_rows(service: IngestionService):
    dto = StartIngestionDTO(filename="logon.csv", initiated_by="u1")
    job = await service.start_ingestion(content=MALFORMED_LOGON, dto=dto)

    assert job.status == "partial"
    assert job.total_rows == 3
    assert job.processed_rows == 3
    assert job.failed_rows == 2
    assert job.events_stored == 1


@pytest.mark.asyncio
async def test_start_ingestion_empty_file_raises(service: IngestionService):
    dto = StartIngestionDTO(filename="empty.csv", initiated_by="u1")
    with pytest.raises(EmptyFileError):
        await service.start_ingestion(content=b"", dto=dto)


@pytest.mark.asyncio
async def test_start_ingestion_unknown_columns_raises(service: IngestionService):
    dto = StartIngestionDTO(filename="bogus.csv", initiated_by="u1")
    with pytest.raises(UnsupportedLogTypeError):
        await service.start_ingestion(content=b"a,b\n1,2\n", dto=dto)


@pytest.mark.asyncio
async def test_start_ingestion_persists_job_metadata(service: IngestionService):
    dto = StartIngestionDTO(
        filename="logon.csv", source_dataset="cert_r4.2", initiated_by="u1"
    )
    job = await service.start_ingestion(content=VALID_LOGON, dto=dto)
    persisted = await service.get_job(uuid.UUID(job.id))
    assert persisted.filename == "logon.csv"
    assert persisted.initiated_by == "u1"


# ─── get_job / list / stats ──────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_not_found(service: IngestionService):
    with pytest.raises(IngestionJobNotFoundError):
        await service.get_job(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_recent_jobs(service: IngestionService):
    dto = StartIngestionDTO(filename="a.csv", initiated_by="u1")
    await service.start_ingestion(content=VALID_LOGON, dto=dto)
    jobs = await service.list_recent_jobs()
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_get_stats_aggregates_correctly(service: IngestionService):
    for name in ["a.csv", "b.csv"]:
        await service.start_ingestion(
            content=VALID_LOGON,
            dto=StartIngestionDTO(filename=name, initiated_by="u1"),
        )
    stats = await service.get_stats()
    assert stats.total_jobs == 2
    assert stats.total_events_stored == 6
    assert stats.jobs_by_log_type.get("logon") == 2


# ─── Events actually reach the store ─────────────────────────


@pytest.mark.asyncio
async def test_events_persisted_to_store(service: IngestionService):
    dto = StartIngestionDTO(filename="logon.csv", initiated_by="u1")
    job = await service.start_ingestion(content=VALID_LOGON, dto=dto)
    count = await service.event_store.count_for_job(job.id)
    assert count == 3


# ─── Errors are persisted ────────────────────────────────────


@pytest.mark.asyncio
async def test_errors_persisted_to_repo(service: IngestionService):
    dto = StartIngestionDTO(filename="logon.csv", initiated_by="u1")
    job = await service.start_ingestion(content=MALFORMED_LOGON, dto=dto)
    errors = await service.error_repo.list_for_job(uuid.UUID(job.id))
    assert len(errors) == 2
    assert all(e.job_id == uuid.UUID(job.id) for e in errors)
