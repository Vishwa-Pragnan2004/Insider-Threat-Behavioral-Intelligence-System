"""
ITBIS — CERT Logon Log Parser

Handles CERT dataset logon.csv variants.
Typical columns (v4.x): id, date, user, pc, activity, logon type
"""
from typing import Any

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class LogonParser(BaseParser):
    """Parses CERT logon activity records."""

    LOG_TYPE = LogType.LOGON
    SOURCE_DATASET = "cert"
    REQUIRED_COLUMNS = {"user", "date", "activity"}

    COLUMN_ALIASES = {
        "user": ["user", "userid", "user_id", "employee"],
        "date": ["date", "timestamp", "datetime", "time"],
        "pc":   ["pc", "machine", "computer", "device", "host"],
        "activity": ["activity", "action", "event_type", "type"],
    }

    # CERT logon activity strings → canonical EventType
    _ACTIVITY_MAP: dict[str, EventType] = {
        "logon": EventType.LOGON,
        "logoff": EventType.LOGOFF,
        "failed logon": EventType.LOGON_FAILED,
        "login": EventType.LOGON,
        "logout": EventType.LOGOFF,
    }

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        raw_id = self.resolve_column(row, "id")
        user_id = self.resolve_required(row, "user", row_number)
        raw_date = self.resolve_required(row, "date", row_number)
        timestamp = self.parse_timestamp(raw_date, row_number)
        activity_raw = (self.resolve_required(row, "activity", row_number) or "").lower().strip()
        event_type = self._ACTIVITY_MAP.get(activity_raw, EventType.SYSTEM_EVENT)
        device_id = self.resolve_column(row, "pc")
        logon_type = (
            self.resolve_column(row, "logon type") or self.resolve_column(row, "logon_type")
        )

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
            action=activity_raw,
            result="success" if event_type != EventType.LOGON_FAILED else "failure",
            raw_payload={**row, "_job_id": job_id},
            enrichments={"logon_type": logon_type} if logon_type else None,
            tags=[self.LOG_TYPE.value],
        )
