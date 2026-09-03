"""
ITBIS — CERT Device/USB Log Parser

Handles CERT dataset device.csv variants.
Typical columns (v4.x): id, date, user, pc, file_tree, activity, content
"""
from typing import Any

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class DeviceParser(BaseParser):
    """Parses CERT removable device (USB) activity records."""

    LOG_TYPE = LogType.DEVICE
    SOURCE_DATASET = "cert"
    # Require the device-specific 'file_tree' column to distinguish from
    # logon records (which share user/date/activity).
    REQUIRED_COLUMNS = {"user", "date", "file_tree"}

    COLUMN_ALIASES = {
        "user":      ["user", "userid", "user_id", "employee"],
        "date":      ["date", "timestamp", "datetime"],
        "pc":        ["pc", "machine", "computer", "device", "host"],
        "activity":  ["activity", "action", "event", "type"],
        "file_tree": ["file_tree", "file", "path", "filename", "filetree"],
        "content":   ["content", "file_content", "data"],
    }

    _ACTIVITY_MAP: dict[str, EventType] = {
        "connect":    EventType.USB_INSERT,
        "disconnect": EventType.USB_REMOVE,
        "read":       EventType.FILE_READ,
        "write":      EventType.USB_FILE_COPY,
        "copy":       EventType.USB_FILE_COPY,
        "open":       EventType.FILE_READ,
    }

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        raw_id = self.resolve_column(row, "id")
        user_id = self.resolve_required(row, "user", row_number)
        raw_date = self.resolve_required(row, "date", row_number)
        timestamp = self.parse_timestamp(raw_date, row_number)
        activity_raw = (self.resolve_required(row, "activity", row_number) or "").lower().strip()
        event_type = self._ACTIVITY_MAP.get(activity_raw, EventType.USB_INSERT)
        device_id = self.resolve_column(row, "pc")
        file_path = self.resolve_column(row, "file_tree")

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
            target_resource=file_path,
            target_type="usb_device" if file_path is None else "file",
            action=activity_raw,
            raw_payload={**row, "_job_id": job_id},
            tags=[self.LOG_TYPE.value, "usb"],
        )
