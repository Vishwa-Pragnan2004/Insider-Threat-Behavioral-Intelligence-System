"""
ITBIS — Activity Module: Base Parser

Every CERT log type adapter implements this interface.
Open/Closed Principle: add new parsers without modifying existing ones.
"""

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from app.modules.activity.domain.enums import LogType
from app.modules.activity.domain.exceptions import MalformedRecordError
from app.shared.schemas.canonical_event import CanonicalEvent


class BaseParser(ABC):
    """
    Abstract base for all CERT log type parsers.

    Each concrete parser handles one CERT log type (logon, device, file, etc.)
    and is responsible for:
      1. Declaring which CSV column signatures it recognises
      2. Transforming a raw CSV row dict into a CanonicalEvent
    """

    # Subclasses must declare this
    LOG_TYPE: LogType
    SOURCE_DATASET: str = "cert"

    # Required columns that MUST be present for this parser to accept the file.
    # Use lowercase column names for comparison.
    REQUIRED_COLUMNS: set[str] = set()

    # Optional alias mappings: canonical_name -> [possible_csv_column_names]
    # Allows schema-flexible ingestion across CERT dataset versions.
    COLUMN_ALIASES: dict[str, list[str]] = {}

    # ── Column resolution helpers ────────────────────────────

    def resolve_column(self, row: dict[str, Any], canonical: str) -> str | None:
        """
        Find the value for a canonical column name, trying aliases.
        Returns None if no matching column found in row.
        """
        # Direct match first
        for key in row:
            if key.lower() == canonical.lower():
                v = row[key]
                return str(v).strip() if v is not None else None

        # Try aliases
        aliases = self.COLUMN_ALIASES.get(canonical, [])
        for alias in aliases:
            for key in row:
                if key.lower() == alias.lower():
                    v = row[key]
                    return str(v).strip() if v is not None else None

        return None

    def resolve_required(self, row: dict[str, Any], canonical: str, row_number: int) -> str:
        """Like resolve_column but raises MalformedRecordError if missing/empty."""
        val = self.resolve_column(row, canonical)
        if not val:
            raise MalformedRecordError(
                row_number=row_number,
                reason=f"Missing required field '{canonical}'",
                raw=row,
            )
        return val

    def parse_timestamp(self, raw: str, row_number: int) -> datetime:
        """
        Parse common CERT timestamp formats into UTC datetime.
        CERT datasets use formats like: '01/02/2010 08:04:42'
        """
        formats = [
            "%m/%d/%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        raw = raw.strip()
        for fmt in formats:
            try:
                dt = datetime.strptime(raw, fmt)
                return dt.replace(tzinfo=UTC)
            except ValueError:
                continue
        raise MalformedRecordError(
            row_number=row_number,
            reason=f"Cannot parse timestamp '{raw}'",
        )

    def safe_int(self, val: str | None) -> int | None:
        """Convert string to int, return None on failure."""
        if val is None:
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    def new_event_id(self) -> uuid.UUID:
        return uuid.uuid4()

    # ── Abstract interface ───────────────────────────────────

    @classmethod
    def can_parse(cls, columns: set[str]) -> bool:
        """
        Return True if this parser can handle a CSV with the given columns.
        Column comparison is case-insensitive and also considers
        parser-specific COLUMN_ALIASES.
        """
        lower_cols = {c.lower() for c in columns}
        # Build the set of column names that satisfy each required canonical
        # field, either by direct match or via a declared alias.
        for canonical in cls.REQUIRED_COLUMNS:
            if canonical in lower_cols:
                continue
            aliases = cls.COLUMN_ALIASES.get(canonical, [])
            if not any(alias.lower() in lower_cols for alias in aliases):
                return False
        return True

    @abstractmethod
    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        """
        Transform a single CSV row dict into a CanonicalEvent.

        Args:
            row: Raw dict from csv.DictReader
            row_number: 1-based row number in the file (for error reporting)
            job_id: UUID string of the parent ingestion job

        Returns:
            A fully populated CanonicalEvent

        Raises:
            MalformedRecordError: on any unrecoverable parse failure for this row
        """
