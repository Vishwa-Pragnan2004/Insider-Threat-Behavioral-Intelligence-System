"""
ITBIS — Activity Module: Domain Exceptions
"""


class ActivityError(Exception):
    """Base error for the activity module."""


class UnsupportedLogTypeError(ActivityError):
    """Raised when a CSV file cannot be matched to any known log type."""


class MalformedRecordError(ActivityError):
    """Raised for a single malformed record — should not abort the job."""
    def __init__(self, row_number: int, reason: str, raw: dict | None = None) -> None:
        self.row_number = row_number
        self.reason = reason
        self.raw = raw
        super().__init__(f"Row {row_number}: {reason}")


class IngestionJobNotFoundError(ActivityError):
    """Raised when querying a non-existent ingestion job."""


class EmptyFileError(ActivityError):
    """Raised when the uploaded CSV file has no data rows."""
