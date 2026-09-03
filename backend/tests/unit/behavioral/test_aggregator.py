"""
ITBIS — Unit tests for the behavioral feature aggregator.
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.behavioral.application.aggregator import (
    aggregate_features,
    iter_daily_windows,
    normalise_window,
)
from app.modules.behavioral.domain.enums import FEATURE_NAMES

# ─── aggregate_features: smoke ─────────────────────────────


def _ev(
    *,
    event_type: str,
    hour: int,
    device_id: str | None = None,
    target_resource: str | None = None,
    risk_indicators: list[str] | None = None,
) -> dict:
    ts = datetime(2026, 8, 30, hour, 0, tzinfo=UTC)
    ev: dict = {"event_type": event_type, "timestamp": ts}
    if device_id is not None:
        ev["device_id"] = device_id
    if target_resource is not None:
        ev["target_resource"] = target_resource
    if risk_indicators is not None:
        ev["risk_indicators"] = risk_indicators
    return ev


def test_aggregate_features_returns_all_keys():
    feats = aggregate_features([])
    for name in FEATURE_NAMES:
        assert name in feats
        assert feats[name] == 0.0


def test_aggregate_features_total_count():
    feats = aggregate_features([
        _ev(event_type="logon", hour=9),
        _ev(event_type="file_read", hour=10),
        _ev(event_type="http_request", hour=11),
    ])
    assert feats["total_activity_count"] == 3


def test_aggregate_features_logon_counts():
    feats = aggregate_features([
        _ev(event_type="logon", hour=9),
        _ev(event_type="logon", hour=10),
        _ev(event_type="logon_failed", hour=11),
        _ev(event_type="logoff", hour=17),
    ])
    assert feats["logon_count"] == 2
    assert feats["failed_logon_count"] == 1


def test_aggregate_features_after_hours_excludes_working_hours():
    feats = aggregate_features([
        _ev(event_type="logon", hour=7),    # before
        _ev(event_type="logon", hour=8),    # boundary (>= 8 is in-hours)
        _ev(event_type="logon", hour=12),
        _ev(event_type="logon", hour=17),   # last in-hour
        _ev(event_type="logon", hour=18),   # after (>= 18 is after-hours)
        _ev(event_type="logon", hour=22),
    ])
    assert feats["after_hours_activity_count"] == 3   # hours 7, 18, 22


def test_aggregate_features_unique_active_hours():
    feats = aggregate_features([
        _ev(event_type="logon", hour=9),
        _ev(event_type="file_read", hour=9),
        _ev(event_type="logon", hour=10),
        _ev(event_type="logon", hour=15),
    ])
    assert feats["unique_active_hours"] == 3   # 9, 10, 15


def test_aggregate_features_unique_devices_and_resources():
    feats = aggregate_features([
        _ev(event_type="logon", hour=9, device_id="WS-1", target_resource=None),
        _ev(event_type="logon", hour=10, device_id="WS-2", target_resource=None),
        _ev(event_type="logon", hour=11, device_id="WS-1", target_resource="file://a"),
        _ev(event_type="logon", hour=12, device_id=None, target_resource="file://a"),
    ])
    assert feats["unique_device_count"] == 2
    assert feats["unique_resource_count"] == 1


def test_aggregate_features_file_counts():
    feats = aggregate_features([
        _ev(event_type="file_read", hour=10),
        _ev(event_type="file_write", hour=10),
        _ev(event_type="file_copy", hour=11),
        _ev(event_type="logon", hour=12),
    ])
    assert feats["file_activity_count"] == 3
    assert feats["file_copy_count"] == 1


def test_aggregate_features_usb_counts():
    feats = aggregate_features([
        _ev(event_type="usb_insert", hour=10),
        _ev(event_type="usb_remove", hour=11),
        _ev(event_type="usb_file_copy", hour=12),
    ])
    assert feats["usb_activity_count"] == 3


def test_aggregate_features_email_counts():
    feats = aggregate_features([
        _ev(event_type="email_sent", hour=10),
        _ev(event_type="email_sent", hour=10, risk_indicators=["external_email"]),
        _ev(event_type="email_external", hour=10),
    ])
    assert feats["email_count"] == 3
    assert feats["external_email_count"] == 2


def test_aggregate_features_http_counts():
    feats = aggregate_features([
        _ev(event_type="http_request", hour=10),
        _ev(event_type="http_upload", hour=10),
        _ev(event_type="http_download", hour=10),
    ])
    assert feats["http_activity_count"] == 3


def test_aggregate_features_ldap_counts():
    feats = aggregate_features([
        _ev(event_type="ldap_query", hour=10),
        _ev(event_type="group_change", hour=10),
        _ev(event_type="password_change", hour=10),
    ])
    assert feats["ldap_activity_count"] == 3


def test_aggregate_features_process_counts():
    feats = aggregate_features([
        _ev(event_type="app_launch", hour=10),
        _ev(event_type="app_close", hour=11),
    ])
    assert feats["process_activity_count"] == 2


def test_aggregate_features_activity_type_diversity():
    feats = aggregate_features([
        _ev(event_type="logon", hour=10),
        _ev(event_type="logon", hour=10),
        _ev(event_type="file_read", hour=10),
        _ev(event_type="http_request", hour=10),
    ])
    assert feats["activity_type_diversity"] == 3


def test_aggregate_features_missing_optional_fields():
    """A canonical event with only event_type + timestamp should not raise."""
    feats = aggregate_features([
        {"event_type": "logon", "timestamp": "2026-08-30T10:00:00+00:00"},
    ])
    assert feats["total_activity_count"] == 1
    assert feats["logon_count"] == 1
    # unique_device_count should be 0 (no device_id field at all)
    assert feats["unique_device_count"] == 0


def test_aggregate_features_handles_string_timestamp_with_z():
    feats = aggregate_features([
        {"event_type": "logon", "timestamp": "2026-08-30T10:00:00Z"},
    ])
    assert feats["total_activity_count"] == 1
    assert feats["logon_count"] == 1


def test_aggregate_features_deterministic():
    events = [
        _ev(event_type="logon", hour=9),
        _ev(event_type="file_read", hour=10, device_id="WS-1"),
        _ev(event_type="http_request", hour=18, device_id="WS-1"),
    ]
    a = aggregate_features(events)
    b = aggregate_features(list(events))
    assert a == b


# ─── normalise_window / iter_daily_windows ────────────────


def test_normalise_window_accepts_naive_datetimes():
    s, e = normalise_window(
        datetime(2026, 8, 1, 0, 0, 0), datetime(2026, 8, 4, 0, 0, 0)
    )
    assert s.tzinfo is not None
    assert e.tzinfo is not None


def test_normalise_window_rejects_inverted():
    with pytest.raises(ValueError):
        normalise_window(
            datetime(2026, 8, 4, tzinfo=UTC),
            datetime(2026, 8, 1, tzinfo=UTC),
        )


def test_iter_daily_windows_three_full_days():
    start = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    end = datetime(2026, 8, 4, 0, 0, 0, tzinfo=UTC)
    windows = list(iter_daily_windows(start, end))
    assert len(windows) == 3
    for (a, b) in windows:
        assert b - a == timedelta(days=1)


def test_iter_daily_windows_partial_first_and_last():
    start = datetime(2026, 8, 1, 8, 30, tzinfo=UTC)
    end = datetime(2026, 8, 2, 16, 0, tzinfo=UTC)
    windows = list(iter_daily_windows(start, end))
    assert len(windows) == 2
    # First window is 8:30 to midnight
    assert windows[0][0].hour == 8 and windows[0][0].minute == 30
    assert windows[0][1].hour == 0 and windows[0][1].day == 2
    # Second window is midnight to 16:00
    assert windows[1][0].hour == 0
    assert windows[1][1].hour == 16
