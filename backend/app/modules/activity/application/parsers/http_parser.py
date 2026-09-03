"""
ITBIS — CERT HTTP/Web Log Parser

Handles CERT dataset http.csv variants.
Typical columns (v4.x): id, date, user, pc, url, activity, content
"""
from typing import Any
from urllib.parse import urlparse

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class HttpParser(BaseParser):
    """Parses CERT HTTP/web browsing activity records."""

    LOG_TYPE = LogType.HTTP
    SOURCE_DATASET = "cert"
    REQUIRED_COLUMNS = {"user", "date", "url"}

    COLUMN_ALIASES = {
        "user":     ["user", "userid", "user_id", "employee"],
        "date":     ["date", "timestamp", "datetime"],
        "pc":       ["pc", "machine", "computer", "device"],
        "url":      ["url", "uri", "website", "destination", "web_address"],
        "activity": ["activity", "action", "method", "type"],
        "bytes":    ["bytes", "size", "content_length", "byte_size"],
    }

    # File upload indicators in URL or content
    _UPLOAD_PATTERNS = [
        "upload", "post", "submit", "send", "webmail",
        "dropbox", "gdrive", "drive.google", "onedrive", "sharepoint",
        "wikisend", "sendspace", "pastebin", "mediafire", "megaupload",
    ]

    def _classify_http(self, url: str, activity: str) -> EventType:
        """Classify HTTP event type from URL and activity."""
        lower_url = url.lower()
        lower_act = activity.lower()
        if any(p in lower_url for p in self._UPLOAD_PATTERNS) or "upload" in lower_act:
            return EventType.HTTP_UPLOAD
        if "download" in lower_act or "download" in lower_url:
            return EventType.HTTP_DOWNLOAD
        return EventType.HTTP_REQUEST

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        raw_id = self.resolve_column(row, "id")
        user_id = self.resolve_required(row, "user", row_number)
        raw_date = self.resolve_required(row, "date", row_number)
        timestamp = self.parse_timestamp(raw_date, row_number)
        url = self.resolve_required(row, "url", row_number)
        activity_raw = (self.resolve_column(row, "activity") or "visit").strip()
        device_id = self.resolve_column(row, "pc")
        bytes_str = self.resolve_column(row, "bytes")

        event_type = self._classify_http(url, activity_raw)

        # Extract domain for enrichment
        try:
            parsed = urlparse(url if url.startswith("http") else f"http://{url}")
            domain = parsed.netloc or url
        except Exception:
            domain = url

        indicators = []
        if event_type == EventType.HTTP_UPLOAD:
            indicators.append("data_upload_detected")

        return CanonicalEvent(
            event_id=self.new_event_id(),
            event_type=event_type,
            source_dataset=self.SOURCE_DATASET,
            raw_event_id=raw_id,
            timestamp=timestamp,
            user_id=user_id,
            username=user_id,
            device_id=device_id,
            target_resource=url,
            target_type="url",
            action=activity_raw,
            bytes_transferred=self.safe_int(bytes_str),
            risk_indicators=indicators,
            raw_payload={**row, "_job_id": job_id},
            enrichments={"domain": domain},
            tags=[self.LOG_TYPE.value],
        )
