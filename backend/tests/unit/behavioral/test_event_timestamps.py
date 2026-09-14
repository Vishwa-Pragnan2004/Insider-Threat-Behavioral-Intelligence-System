"""
ITBIS — Unit tests: event timestamp handling in feature generation.

Regression: the continuous pipeline's first run against real data failed with
"TypeError: can't compare offset-naive and offset-aware datetimes". Endpoint
agent events had been stored with timestamps carrying no UTC offset, and one
such event aborted the whole feature run for every user.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.modules.behavioral.application.services.feature_engineering_service import (
    FeatureEngineeringService,
    _ts,
)

DAY = datetime(2026, 9, 14, tzinfo=UTC)
EPOCH = datetime.fromtimestamp(0, tz=UTC)


def test_utc_string_with_z():
    assert _ts({"timestamp": "2026-09-14T09:00:00Z"}) == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_string_with_an_offset_is_converted():
    assert _ts({"timestamp": "2026-09-14T14:30:00+05:30"}) == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_string_without_an_offset_is_treated_as_utc():
    parsed = _ts({"timestamp": "2026-09-14T09:00:00"})
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_naive_datetime_from_mongodb_is_treated_as_utc():
    parsed = _ts({"timestamp": datetime(2026, 9, 14, 9)})
    assert parsed == datetime(2026, 9, 14, 9, tzinfo=UTC)


def test_missing_or_unparseable_timestamps_fall_outside_every_window():
    assert _ts({}) == EPOCH
    assert _ts({"timestamp": "not a date"}) == EPOCH


def test_daily_features_accept_a_mix_of_naive_and_aware_timestamps():
    service = FeatureEngineeringService(feature_store=None, baseline_repo=None, event_source=None)
    events = [
        {"event_type": "logon", "user_id": "u", "timestamp": "2026-09-14T09:00:00"},
        {"event_type": "logon", "user_id": "u", "timestamp": "2026-09-14T10:00:00Z"},
        {"event_type": "logon", "user_id": "u", "timestamp": datetime(2026, 9, 14, 11)},
    ]

    rows = service._features_daily("u", events, "all", DAY, DAY + timedelta(days=1))

    assert len(rows) == 1
    assert rows[0].event_count == 3
