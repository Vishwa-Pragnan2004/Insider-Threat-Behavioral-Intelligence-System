"""
ITBIS — CERT File Activity Log Parser

Handles CERT dataset file.csv variants.
Typical columns (v4.x): id, date, user, pc, filename, activity, content

Release r4.2 has no activity column: there every row is a file copied to
removable media (see the dataset readme), so a missing activity means "copy".
"""
from typing import Any

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class FileParser(BaseParser):
    """Parses CERT file activity (read/write/delete/copy/print) records."""

    LOG_TYPE = LogType.FILE
    SOURCE_DATASET = "cert"
    REQUIRED_COLUMNS = {"user", "date", "filename"}

    COLUMN_ALIASES = {
        "user":     ["user", "userid", "user_id", "employee"],
        "date":     ["date", "timestamp", "datetime"],
        "pc":       ["pc", "machine", "computer", "device", "host"],
        "filename": ["filename", "file", "path", "filepath", "file_path", "file_name"],
        "activity": ["activity", "action", "event", "type"],
    }

    _ACTIVITY_MAP: dict[str, EventType] = {
        "open":     EventType.FILE_READ,
        "read":     EventType.FILE_READ,
        "write":    EventType.FILE_WRITE,
        "delete":   EventType.FILE_DELETE,
        "copy":     EventType.FILE_COPY,
        "move":     EventType.FILE_MOVE,
        "rename":   EventType.FILE_MOVE,
        "print":    EventType.FILE_PRINT,
        "upload":   EventType.FILE_UPLOAD,
        "download": EventType.FILE_DOWNLOAD,
    }

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        raw_id = self.resolve_column(row, "id")
        user_id = self.resolve_required(row, "user", row_number)
        raw_date = self.resolve_required(row, "date", row_number)
        timestamp = self.parse_timestamp(raw_date, row_number)
        filename = self.resolve_required(row, "filename", row_number)
        activity_raw = (self.resolve_column(row, "activity") or "copy").lower().strip()
        event_type = self._ACTIVITY_MAP.get(activity_raw, EventType.FILE_READ)
        device_id = self.resolve_column(row, "pc")

        return CanonicalEvent(
            event_id=self.new_event_id(),
            event_type=event_type,
            source_dataset=self.SOURCE_DATASET,
            raw_event_id=raw_id,
            timestamp=timestamp,
            user_id=user_id,
            username=user_id,
            device_id=device_id,
            device_name=device_id,
            target_resource=filename,
            target_type="removable_media" if event_type == EventType.FILE_COPY else "file",
            action=activity_raw,
            risk_indicators=(
                ["file_copied_to_removable_media"] if event_type == EventType.FILE_COPY else []
            ),
            raw_payload={**row, "_job_id": job_id},
            tags=[self.LOG_TYPE.value],
        )
