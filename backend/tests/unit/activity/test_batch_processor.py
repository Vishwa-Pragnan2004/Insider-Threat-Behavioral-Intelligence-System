"""
ITBIS — Unit tests for the BatchProcessor.

Exercises chunked streaming, malformed-row isolation, and header utilities.
"""
import pytest

from app.modules.activity.application.parsers.logon_parser import LogonParser
from app.modules.activity.application.services.batch_processor import BatchProcessor

JOB_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def processor() -> BatchProcessor:
    return BatchProcessor(parser=LogonParser(), chunk_size=3)


VALID_LOGON_CSV = (
    b"id,date,user,pc,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"
    b"2,01/02/2010 17:00:00,alice,PC1,Logoff\n"
    b"3,01/02/2010 08:05:00,bob,PC2,Logon\n"
    b"4,01/02/2010 17:05:00,bob,PC2,Logoff\n"
    b"5,01/03/2010 08:00:00,alice,PC1,Logon\n"
)

MALFORMED_CSV = (
    b"id,date,user,pc,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"        # OK
    b"2,NOTADATE,alice,PC1,Logoff\n"                  # bad timestamp
    b"3,01/02/2010 08:05:00,,PC2,Logon\n"             # missing user
    b"4,01/02/2010 17:05:00,bob,PC2,Logoff\n"         # OK
)

EMPTY_CSV = b"id,date,user,pc,activity\n"


# ─── read_columns ────────────────────────────────────────────


def test_read_columns(processor):
    cols = processor.read_columns(VALID_LOGON_CSV)
    assert "user" in cols
    assert "date" in cols
    assert "activity" in cols


def test_read_columns_handles_bom(processor):
    csv_with_bom = b"\xef\xbb\xbf" + VALID_LOGON_CSV
    cols = processor.read_columns(csv_with_bom)
    assert "user" in cols


# ─── count_rows ──────────────────────────────────────────────


def test_count_rows(processor):
    assert processor.count_rows(VALID_LOGON_CSV) == 5


def test_count_rows_empty(processor):
    assert processor.count_rows(EMPTY_CSV) == 0


# ─── iter_chunks ─────────────────────────────────────────────


def test_iter_chunks_happy_path(processor):
    chunks = list(processor.iter_chunks(VALID_LOGON_CSV, job_id=JOB_ID))
    total_events = sum(len(c.events) for c in chunks)
    total_errors = sum(len(c.errors) for c in chunks)
    assert total_events == 5
    assert total_errors == 0
    assert len(chunks) >= 2  # chunk_size=3 -> at least 2 chunks for 5 rows


def test_iter_chunks_yields_correct_events(processor):
    chunks = list(processor.iter_chunks(VALID_LOGON_CSV, job_id=JOB_ID))
    events = [e for c in chunks for e in c.events]
    users = {e.user_id for e in events}
    assert users == {"alice", "bob"}


def test_iter_chunks_isolates_malformed_rows(processor):
    """Malformed rows must NOT abort the job — they should be recorded as errors."""
    chunks = list(processor.iter_chunks(MALFORMED_CSV, job_id=JOB_ID))
    total_events = sum(len(c.events) for c in chunks)
    total_errors = sum(len(c.errors) for c in chunks)
    assert total_events == 2  # rows 1 and 4
    assert total_errors == 2  # rows 2 and 3

    # Verify error details
    all_errors = [e for c in chunks for e in c.errors]
    row_numbers = sorted(e.row_number for e in all_errors)
    assert row_numbers == [3, 4]  # 1-based (header is row 1, first data row is row 2)


def test_iter_chunks_empty_file(processor):
    chunks = list(processor.iter_chunks(EMPTY_CSV, job_id=JOB_ID))
    total_events = sum(len(c.events) for c in chunks)
    assert total_events == 0


def test_iter_chunks_chunk_size_one():
    proc = BatchProcessor(parser=LogonParser(), chunk_size=1)
    chunks = list(proc.iter_chunks(VALID_LOGON_CSV, job_id=JOB_ID))
    # 5 rows with chunk_size=1 → each chunk holds at most 1 item
    assert len(chunks) == 5
    for c in chunks:
        assert len(c.events) + len(c.errors) == 1


def test_iter_chunks_preserves_raw_payload(processor):
    chunks = list(processor.iter_chunks(VALID_LOGON_CSV, job_id=JOB_ID))
    events = [e for c in chunks for e in c.events]
    first = events[0]
    assert first.raw_payload is not None
    assert first.raw_payload["user"] == "alice"
    assert first.raw_payload["_job_id"] == JOB_ID


# ─── Row-number tracking ────────────────────────────────────


def test_iter_chunks_row_number_uses_1_based(processor):
    chunks = list(processor.iter_chunks(MALFORMED_CSV, job_id=JOB_ID))
    all_errors = [e for c in chunks for e in c.errors]
    # The bad-timestamp row is the 2nd data row → row_number=3
    bad_ts = next(e for e in all_errors if "timestamp" in e.reason.lower())
    assert bad_ts.row_number == 3


# ─── Unexpected errors are also caught ───────────────────────


def test_iter_chunks_catches_unexpected_exceptions():
    """A bug in the parser (e.g. AttributeError) must be caught and recorded."""

    class _BuggyParser:
        LOG_TYPE = None
        REQUIRED_COLUMNS = set()
        COLUMN_ALIASES = {}

        def parse_row(self, row, row_number, job_id):
            raise RuntimeError("boom")

        @classmethod
        def can_parse(cls, columns):
            return True

    proc = BatchProcessor(parser=_BuggyParser(), chunk_size=10)  # type: ignore[arg-type]
    csv = b"a,b\n1,2\n3,4\n"
    chunks = list(proc.iter_chunks(csv, job_id=JOB_ID))
    errors = [e for c in chunks for e in c.errors]
    assert len(errors) == 2
    assert all("boom" in e.reason for e in errors)
