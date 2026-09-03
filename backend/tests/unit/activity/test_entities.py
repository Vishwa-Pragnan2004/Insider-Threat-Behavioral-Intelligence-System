"""
ITBIS — Unit tests for the domain entities.
"""
import uuid
from datetime import datetime

from app.modules.activity.domain.entities import IngestionError, IngestionJob
from app.modules.activity.domain.enums import JobStatus, LogType


def test_ingestion_job_defaults():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
    )
    assert j.status == JobStatus.PENDING
    assert j.total_rows == 0
    assert j.success_rate == 0.0


def test_ingestion_job_success_rate():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
        total_rows=10,
        processed_rows=8,
        failed_rows=2,
    )
    assert j.success_rate == 60.0


def test_ingestion_job_mark_running():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
    )
    j.mark_running()
    assert j.status == JobStatus.RUNNING
    assert j.started_at is not None


def test_ingestion_job_mark_completed_clean():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
        total_rows=5,
        processed_rows=5,
        failed_rows=0,
    )
    j.mark_running()
    j.mark_completed()
    assert j.status == JobStatus.COMPLETED
    assert j.completed_at is not None


def test_ingestion_job_mark_completed_with_errors_is_partial():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
        total_rows=5,
        processed_rows=5,
        failed_rows=2,
    )
    j.mark_running()
    j.mark_completed()
    assert j.status == JobStatus.PARTIAL


def test_ingestion_job_mark_failed():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
    )
    j.mark_failed("parser exploded")
    assert j.status == JobStatus.FAILED
    assert j.error_message == "parser exploded"
    assert j.completed_at is not None


def test_ingestion_job_increments():
    j = IngestionJob(
        id=uuid.uuid4(),
        filename="x.csv",
        log_type=LogType.LOGON,
        source_dataset="cert",
    )
    j.increment_processed(3)
    j.increment_processed(2)
    j.increment_failed(1)
    j.increment_stored(4)
    assert j.processed_rows == 5
    assert j.failed_rows == 1
    assert j.events_stored == 4


def test_ingestion_error_defaults():
    e = IngestionError()
    assert e.row_number == 0
    assert e.reason == ""
    assert isinstance(e.occurred_at, datetime)
