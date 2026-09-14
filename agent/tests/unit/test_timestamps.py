"""
Agent timestamp handling.

Regressions:
  - Windows Security events were sent with TimeGenerated's naive *local* time,
    so they were stored hours off and without a timezone, which crashed the
    server's feature generation.
  - WMI CIM_DATETIME offsets are minutes ("+330"), which strptime's %z
    rejects; every process timestamp silently became "now".
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from itbis_agent._utils import _parse_iso
from itbis_agent.collectors.windows_security import event_time_utc


def test_utc_iso_string():
    assert _parse_iso("2026-09-14T09:00:00+00:00") == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_z_iso_string():
    assert _parse_iso("2026-09-14T09:00:00Z") == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_iso_string_with_an_offset():
    assert _parse_iso("2026-09-14T14:30:00+05:30") == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_naive_iso_string_is_host_local_time():
    local = datetime(2026, 9, 14, 17, 55, 6)
    parsed = _parse_iso(local.isoformat())
    assert parsed.tzinfo is not None
    assert parsed == local.astimezone(UTC)


def test_naive_datetime_is_host_local_time():
    local = datetime(2026, 9, 14, 17, 55, 6)
    assert _parse_iso(local) == local.astimezone(UTC)


@pytest.mark.parametrize(
    ("cim", "expected_utc"),
    [
        ("20260914140608.000000+330", datetime(2026, 9, 14, 8, 36, 8, tzinfo=UTC)),
        ("20260914140608.250000-300", datetime(2026, 9, 14, 19, 6, 8, 250000, tzinfo=UTC)),
        ("20260914140608.000000+000", datetime(2026, 9, 14, 14, 6, 8, tzinfo=UTC)),
    ],
)
def test_wmi_cim_datetime_offset_is_in_minutes(cim, expected_utc):
    assert _parse_iso(cim) == expected_utc


@pytest.mark.parametrize("value", [None, "", "not a timestamp", 12345])
def test_unparseable_values_fall_back_to_now_in_utc(value):
    before = datetime.now(UTC)
    parsed = _parse_iso(value)
    assert parsed.tzinfo is not None
    assert before - timedelta(seconds=1) <= parsed <= datetime.now(UTC) + timedelta(seconds=1)


def test_event_log_time_is_sent_as_utc():
    local = datetime(2026, 9, 14, 17, 55, 6)  # what pywin32's TimeGenerated looks like
    sent = event_time_utc(local)
    assert sent.endswith("+00:00")
    assert datetime.fromisoformat(sent) == local.astimezone(UTC)


def test_aware_event_log_time_is_converted_not_relabelled():
    ist = datetime(2026, 9, 14, 14, 6, 8, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert event_time_utc(ist) == "2026-09-14T08:36:08+00:00"


def test_missing_event_log_time():
    assert event_time_utc(None) is None
