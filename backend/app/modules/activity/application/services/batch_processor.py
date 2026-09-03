"""
ITBIS — Activity Module: Batch Processor

Reads a CSV file in memory-efficient chunks and routes each row
to the appropriate parser. Collects results and errors without
crashing on individual bad records.
"""
import csv
import io
import logging
from collections.abc import Iterator

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.entities import IngestionError
from app.modules.activity.domain.exceptions import MalformedRecordError
from app.shared.schemas.canonical_event import CanonicalEvent

logger = logging.getLogger(__name__)


class BatchResult:
    """Result of processing one chunk of rows."""
    __slots__ = ("events", "errors")

    def __init__(self) -> None:
        self.events: list[CanonicalEvent] = []
        self.errors: list[IngestionError] = []


class BatchProcessor:
    """
    Reads a CSV byte-stream in row-by-row chunks and delegates
    each row to the appropriate parser.

    Design decisions:
    - chunk_size controls how many rows are buffered before yielding
    - MalformedRecordErrors are caught per-row and recorded as IngestionErrors
    - Other unexpected exceptions are also caught to prevent job crash
    """

    def __init__(self, parser: BaseParser, chunk_size: int = 500) -> None:
        self.parser = parser
        self.chunk_size = chunk_size

    def iter_chunks(
        self,
        content: bytes,
        job_id: str,
        encoding: str = "utf-8-sig",
    ) -> Iterator[BatchResult]:
        """
        Parse CSV content into chunks of CanonicalEvents.

        Args:
            content: Raw CSV file bytes
            job_id: UUID string of the parent IngestionJob
            encoding: CSV encoding (utf-8-sig strips BOM)

        Yields:
            BatchResult containing events and errors for each chunk
        """
        text = content.decode(encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        chunk = BatchResult()
        row_number = 1  # 1-based (header is row 0)

        for raw_row in reader:
            row_number += 1
            try:
                event = self.parser.parse_row(raw_row, row_number, job_id)
                chunk.events.append(event)
            except MalformedRecordError as exc:
                import uuid as _uuid
                chunk.errors.append(
                    IngestionError(
                        id=_uuid.uuid4(),
                        job_id=_uuid.UUID(job_id),
                        row_number=exc.row_number,
                        reason=exc.reason,
                        raw_data=exc.raw,
                    )
                )
            except Exception as exc:
                import uuid as _uuid
                logger.warning(
                    "Unexpected error on row %d: %s",
                    row_number,
                    str(exc),
                    exc_info=False,
                )
                chunk.errors.append(
                    IngestionError(
                        id=_uuid.uuid4(),
                        job_id=_uuid.UUID(job_id),
                        row_number=row_number,
                        reason=f"Unexpected error: {exc}",
                        raw_data=dict(raw_row),
                    )
                )

            if len(chunk.events) + len(chunk.errors) >= self.chunk_size:
                yield chunk
                chunk = BatchResult()

        # Yield remaining rows
        if chunk.events or chunk.errors:
            yield chunk

    def count_rows(self, content: bytes, encoding: str = "utf-8-sig") -> int:
        """Count data rows in CSV without parsing (for total_rows metadata)."""
        text = content.decode(encoding, errors="replace")
        lines = text.strip().splitlines()
        return max(0, len(lines) - 1)  # subtract header

    def read_columns(self, content: bytes, encoding: str = "utf-8-sig") -> set[str]:
        """Read only the header row and return the column name set."""
        text = content.decode(encoding, errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return set(reader.fieldnames or [])
