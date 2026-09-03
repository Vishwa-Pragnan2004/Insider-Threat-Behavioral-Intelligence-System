"""
ITBIS — CERT Email Log Parser

Handles CERT dataset email.csv variants.
Typical columns (v4.x): id, date, user, pc, to, from, activity, size, attachments, content
"""
from typing import Any

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class EmailParser(BaseParser):
    """Parses CERT email activity records."""

    LOG_TYPE = LogType.EMAIL
    SOURCE_DATASET = "cert"
    # An email record must have at least a recipient column ('to' or 'from')
    # to distinguish it from logon/device/file/lDAP records that share
    # the generic (user, date, activity) shape.
    REQUIRED_COLUMNS = {"user", "date", "to"}

    COLUMN_ALIASES = {
        "user":        ["user", "userid", "user_id", "from", "sender"],
        "date":        ["date", "timestamp", "datetime"],
        "pc":          ["pc", "machine", "computer", "device"],
        "to":          ["to", "recipient", "recipients", "to_address"],
        "activity":    ["activity", "action", "event", "type"],
        "size":        ["size", "email_size", "bytes", "byte_size"],
        "attachments": ["attachments", "attachment_count", "num_attachments"],
    }

    def _is_external(self, to_addr: str | None, from_addr: str | None) -> bool:
        """Heuristic: if to address is outside @dtaa.com (CERT domain) it's external."""
        cert_domain = "dtaa.com"
        if to_addr and "@" in to_addr:
            # Could be a list
            addrs = [a.strip() for a in to_addr.replace(";", ",").split(",")]
            return any(cert_domain not in a for a in addrs if "@" in a)
        return False

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        raw_id = self.resolve_column(row, "id")
        user_id = self.resolve_required(row, "user", row_number)
        raw_date = self.resolve_required(row, "date", row_number)
        timestamp = self.parse_timestamp(raw_date, row_number)
        activity_raw = (self.resolve_column(row, "activity") or "send").lower().strip()
        device_id = self.resolve_column(row, "pc")
        to_addr = self.resolve_column(row, "to")
        size_str = self.resolve_column(row, "size")
        attach_str = self.resolve_column(row, "attachments")

        is_external = self._is_external(to_addr, user_id)
        event_type = EventType.EMAIL_EXTERNAL if is_external else EventType.EMAIL_SENT

        indicators = []
        if is_external:
            indicators.append("external_email")
        attach_count = self.safe_int(attach_str)
        if attach_count and attach_count > 0:
            indicators.append("has_attachments")

        return CanonicalEvent(
            event_id=self.new_event_id(),
            event_type=event_type,
            source_dataset=self.SOURCE_DATASET,
            raw_event_id=raw_id,
            timestamp=timestamp,
            user_id=user_id,
            username=user_id,
            device_id=device_id,
            target_resource=to_addr,
            target_type="email",
            action=activity_raw,
            bytes_transferred=self.safe_int(size_str),
            file_count=attach_count,
            risk_indicators=indicators,
            raw_payload={**row, "_job_id": job_id},
            tags=[self.LOG_TYPE.value],
        )
