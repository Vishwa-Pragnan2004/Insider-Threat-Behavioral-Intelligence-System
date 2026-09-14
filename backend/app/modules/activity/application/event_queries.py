"""
ITBIS — Activity Module: canonical event queries

Read side of the event store, for people rather than the pipeline: page
through raw events (agent telemetry and CERT uploads) and summarise recent
activity. Used by the activity API and the SOC dashboard.

Event timestamps are stored as ISO-8601 strings, not BSON dates, and not
always with the same suffix ("…Z", "…+00:00", or none). Range filters compare
against a suffix-free "YYYY-MM-DDTHH:MM:SS" prefix, which sorts correctly
against all of them.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "canonical_events"
#: Upper bound on events read into memory for one summary.
SUMMARY_SCAN_LIMIT = 200_000

_VIEW_FIELDS = {
    "event_id": 1, "event_type": 1, "timestamp": 1, "user_id": 1, "device_id": 1,
    "device_name": 1, "source_dataset": 1, "target_resource": 1, "target_type": 1,
    "action": 1, "result": 1, "ip_address": 1, "is_remote": 1, "risk_indicators": 1,
    "tags": 1, "enrichments": 1, "ingested_at": 1,
}


def as_utc(value: Any) -> datetime | None:
    """A stored timestamp (datetime or ISO string, naive means UTC) as an aware UTC datetime."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def iso(value: Any) -> str | None:
    parsed = as_utc(value)
    if parsed is not None:
        return parsed.isoformat().replace("+00:00", "Z")
    return str(value) if value is not None else None


def timestamp_bound(value: datetime) -> str:
    """The string to range-compare stored ISO timestamps against."""
    return (as_utc(value) or value).strftime("%Y-%m-%dT%H:%M:%S")


def event_view(doc: dict) -> dict:
    """A stored event as the API shows it (the raw collector payload is left out)."""
    event_id = doc.get("event_id")
    return {
        "id": str(doc.get("_id")),
        "event_id": str(event_id) if event_id is not None else None,
        "event_type": doc.get("event_type") or "unknown",
        "timestamp": iso(doc.get("timestamp")),
        "user_id": doc.get("user_id") or "unknown",
        "device_id": doc.get("device_id"),
        "device_name": doc.get("device_name"),
        "source_dataset": doc.get("source_dataset") or "unknown",
        "target_resource": doc.get("target_resource"),
        "target_type": doc.get("target_type"),
        "action": doc.get("action"),
        "result": doc.get("result"),
        "ip_address": doc.get("ip_address"),
        "is_remote": doc.get("is_remote"),
        "risk_indicators": list(doc.get("risk_indicators") or []),
        "tags": list(doc.get("tags") or []),
        "enrichments": doc.get("enrichments") or None,
        "ingested_at": iso(doc.get("ingested_at")),
    }


@dataclass(frozen=True)
class EventFilters:
    user_id: str | None = None
    event_type: str | None = None
    source_dataset: str | None = None
    device_id: str | None = None
    start: datetime | None = None
    end: datetime | None = None

    def query(self) -> dict:
        q: dict[str, Any] = {
            field: value
            for field, value in (
                ("user_id", self.user_id),
                ("event_type", self.event_type),
                ("source_dataset", self.source_dataset),
                ("device_id", self.device_id),
            )
            if value
        }
        if self.start or self.end:
            q["timestamp"] = {}
            if self.start:
                q["timestamp"]["$gte"] = timestamp_bound(self.start)
            if self.end:
                q["timestamp"]["$lt"] = timestamp_bound(self.end)
        return q


class EventQueries:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._events = db[COLLECTION]

    async def list_events(
        self, filters: EventFilters, *, skip: int = 0, limit: int = 50
    ) -> tuple[list[dict], int]:
        """Newest first."""
        query = filters.query()
        total = await self._events.count_documents(query)
        cursor = (
            self._events.find(query, _VIEW_FIELDS)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )
        return [event_view(doc) async for doc in cursor], total

    async def summary(self, *, hours: int = 24, now: datetime | None = None) -> dict:
        """Counts over the last `hours`, with one bucket per hour (oldest first)."""
        now = as_utc(now) or datetime.now(UTC)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        first_hour = current_hour - timedelta(hours=hours - 1)
        buckets = {first_hour + timedelta(hours=i): 0 for i in range(hours)}

        by_type: Counter[str] = Counter()
        by_source: Counter[str] = Counter()
        by_user: Counter[str] = Counter()
        devices: set[str] = set()
        total = flagged = 0
        cursor = self._events.find(
            {"timestamp": {"$gte": timestamp_bound(first_hour)}},
            {"event_type": 1, "source_dataset": 1, "user_id": 1, "device_id": 1,
             "timestamp": 1, "risk_indicators": 1},
        ).limit(SUMMARY_SCAN_LIMIT)
        async for doc in cursor:
            when = as_utc(doc.get("timestamp"))
            if when is None or when > now:
                continue
            total += 1
            by_type[doc.get("event_type") or "unknown"] += 1
            by_source[doc.get("source_dataset") or "unknown"] += 1
            by_user[doc.get("user_id") or "unknown"] += 1
            if doc.get("device_id"):
                devices.add(doc["device_id"])
            if doc.get("risk_indicators"):
                flagged += 1
            hour = when.replace(minute=0, second=0, microsecond=0)
            if hour in buckets:
                buckets[hour] += 1

        return {
            "window_hours": hours,
            "total": total,
            "flagged": flagged,
            "active_users": len(by_user),
            "active_devices": len(devices),
            "by_event_type": dict(by_type.most_common()),
            "by_source": dict(by_source.most_common()),
            "top_users": [{"user_id": u, "count": c} for u, c in by_user.most_common(10)],
            "hourly": [{"hour": iso(hour), "count": count} for hour, count in buckets.items()],
        }

    async def recent(self, limit: int = 15) -> list[dict]:
        events, _ = await self.list_events(EventFilters(), limit=limit)
        return events

    def find(self, query: dict, projection: dict | None = None):  # noqa: ANN201 - motor cursor
        return self._events.find(query, projection)
