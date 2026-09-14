"""Helpers shared across the agent."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any


def _to_utc(value: datetime) -> datetime:
    """
    Aware UTC datetime.

    A naive value is the host's local time (what Windows APIs such as the event
    log's TimeGenerated return), so it is converted from local time rather than
    merely labelled UTC, which would shift it by the host's UTC offset.
    """
    return value.astimezone(UTC)


def _parse_cim_datetime(value: str) -> datetime | None:
    """
    Parse a WMI CIM_DATETIME such as "20260914140608.123456+330".

    The trailing offset is in minutes, not HHMM, so strptime's %z rejects it;
    that used to make every WMI timestamp silently fall back to "now".
    """
    if len(value) != 25 or value[14] != "." or value[21] not in "+-":
        return None
    try:
        local = datetime.strptime(value[:21], "%Y%m%d%H%M%S.%f")
        minutes = int(value[22:])
    except ValueError:
        return None
    sign = 1 if value[21] == "+" else -1
    offset = timezone(timedelta(minutes=sign * minutes))
    return local.replace(tzinfo=offset).astimezone(UTC)


def _parse_iso(value: Any) -> datetime:
    """Parse an agent timestamp into an aware UTC datetime; falls back to now (UTC)."""
    if isinstance(value, datetime):
        return _to_utc(value)
    if not value or not isinstance(value, str):
        return datetime.now(UTC)
    cim = _parse_cim_datetime(value)
    if cim is not None:
        return cim
    try:
        return _to_utc(datetime.fromisoformat(value))
    except ValueError:
        return datetime.now(UTC)
