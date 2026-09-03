"""
ITBIS — CERT LDAP Log Parser

Handles CERT dataset ldap.csv variants.
Typical columns (v4.x): id, date, user, pc, activity, object_accessed
"""
from typing import Any

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.shared.schemas.canonical_event import CanonicalEvent, EventType


class LdapParser(BaseParser):
    """Parses CERT LDAP / Active Directory activity records."""

    LOG_TYPE = LogType.LDAP
    SOURCE_DATASET = "cert"
    # Require the LDAP-specific 'object_accessed' column to disambiguate from
    # logon/device records that also have user+date.
    REQUIRED_COLUMNS = {"user", "date", "object_accessed"}

    COLUMN_ALIASES = {
        "user":            ["user", "userid", "user_id", "employee", "subject"],
        "date":            ["date", "timestamp", "datetime"],
        "pc":              ["pc", "machine", "computer", "device"],
        "activity":        ["activity", "action", "event", "type"],
        "object_accessed": ["object_accessed", "object", "target", "resource", "attribute"],
    }

    _ACTIVITY_MAP: dict[str, EventType] = {
        "ldap_query":    EventType.LDAP_QUERY,
        "ldap query":    EventType.LDAP_QUERY,
        "search":        EventType.LDAP_QUERY,
        "query":         EventType.LDAP_QUERY,
        "group_change":  EventType.GROUP_CHANGE,
        "group change":  EventType.GROUP_CHANGE,
        "privilege":     EventType.PRIVILEGE_CHANGE,
        "password":      EventType.PASSWORD_CHANGE,
        "create":        EventType.ACCOUNT_CREATED,
        "disable":       EventType.ACCOUNT_DISABLED,
    }

    def parse_row(self, row: dict[str, Any], row_number: int, job_id: str) -> CanonicalEvent:
        raw_id = self.resolve_column(row, "id")
        user_id = self.resolve_required(row, "user", row_number)
        raw_date = self.resolve_required(row, "date", row_number)
        timestamp = self.parse_timestamp(raw_date, row_number)
        activity_raw = (self.resolve_column(row, "activity") or "ldap_query").lower().strip()
        device_id = self.resolve_column(row, "pc")
        obj = self.resolve_column(row, "object_accessed")

        event_type = EventType.LDAP_QUERY
        for key, etype in self._ACTIVITY_MAP.items():
            if key in activity_raw:
                event_type = etype
                break

        return CanonicalEvent(
            event_id=self.new_event_id(),
            event_type=event_type,
            source_dataset=self.SOURCE_DATASET,
            raw_event_id=raw_id,
            timestamp=timestamp,
            user_id=user_id,
            username=user_id,
            device_id=device_id,
            target_resource=obj,
            target_type="ldap_object",
            action=activity_raw,
            raw_payload={**row, "_job_id": job_id},
            tags=[self.LOG_TYPE.value, "ldap"],
        )
