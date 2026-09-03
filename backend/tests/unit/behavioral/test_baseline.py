"""
ITBIS — Unit tests for the baseline builder.

Covers:
  - basic stats (mean, std, min, max, count)
  - empty data
  - future-data leakage prevention
  - update_baseline combination logic
"""
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.behavioral.application.baseline import (
    build_baseline,
    update_baseline,
)

HISTORY_START = datetime(2026, 8, 1, tzinfo=UTC)
HISTORY_END = datetime(2026, 8, 8, tzinfo=UTC)


def _row(day: int, **features: float) -> dict:
    """Build a daily feature row for day 1..7 in the history window."""
    return {
        "window_start": HISTORY_START + timedelta(days=day - 1),
        "window_end": HISTORY_START + timedelta(days=day),
        "features": features,
    }


def test_build_baseline_basic_stats():
    daily = [
        _row(1, logon_count=10, file_read=5),
        _row(2, logon_count=12, file_read=4),
        _row(3, logon_count=8, file_read=6),
    ]
    stats = build_baseline(daily, history_start=HISTORY_START, history_end=HISTORY_END)
    assert stats["logon_count"]["mean"] == pytest.approx(10.0)
    assert stats["logon_count"]["count"] == 3
    assert stats["logon_count"]["min"] == 8.0
    assert stats["logon_count"]["max"] == 12.0
    assert stats["file_read"]["mean"] == pytest.approx(5.0)


def test_build_baseline_empty_returns_empty_dict():
    stats = build_baseline([], history_start=HISTORY_START, history_end=HISTORY_END)
    assert stats == {}


def test_build_baseline_rejects_inverted_window():
    with pytest.raises(ValueError):
        build_baseline([], history_start=HISTORY_END, history_end=HISTORY_START)


def test_build_baseline_rejects_equal_window():
    with pytest.raises(ValueError):
        build_baseline([], history_start=HISTORY_START, history_end=HISTORY_START)


# ─── Leakage prevention ────────────────────────────────────


def test_build_baseline_excludes_future_rows():
    daily = [
        _row(1, logon_count=10),
        _row(7, logon_count=99),     # last valid day
        _row(8, logon_count=999),   # EXACTLY on history_end boundary — must be excluded
        _row(9, logon_count=9999),  # past the boundary — must be excluded
    ]
    stats = build_baseline(
        daily, history_start=HISTORY_START, history_end=HISTORY_END
    )
    # Mean should be (10+99)/2 = 54.5 — not polluted by 999/9999
    assert stats["logon_count"]["mean"] == pytest.approx(54.5)
    assert stats["logon_count"]["max"] == 99.0


def test_build_baseline_excludes_rows_outside_history():
    daily = [
        _row(1, logon_count=10),
        _row(0, logon_count=1),   # before history_start
        _row(100, logon_count=1),  # after history_end
    ]
    stats = build_baseline(
        daily, history_start=HISTORY_START, history_end=HISTORY_END
    )
    assert stats["logon_count"]["mean"] == 10.0


def test_build_baseline_partial_overlap_uses_capped_window():
    """A row that straddles the boundary should be safely excluded entirely
    (we don't currently prorate; we just refuse to include it)."""
    # A row that starts before history_end and ends after it
    bad_row = {
        "window_start": HISTORY_END - timedelta(hours=1),
        "window_end": HISTORY_END + timedelta(hours=1),
        "features": {"logon_count": 99},
    }
    safe_row = _row(1, logon_count=10)
    stats = build_baseline(
        [safe_row, bad_row], history_start=HISTORY_START, history_end=HISTORY_END
    )
    assert stats["logon_count"]["mean"] == 10.0


# ─── update_baseline ──────────────────────────────────────


def test_update_baseline_with_no_existing():
    daily = [_row(1, logon_count=10), _row(2, logon_count=20)]
    stats = update_baseline(
        None,
        daily,
        history_start=HISTORY_START,
        history_end=HISTORY_END,
    )
    assert stats["logon_count"]["mean"] == 15.0


def test_update_baseline_combines_old_and_new():
    existing = {"logon_count": {"mean": 10.0, "std": 1.0, "min": 9.0, "max": 11.0, "count": 2}}
    new = [_row(1, logon_count=20), _row(2, logon_count=30)]
    combined = update_baseline(
        existing,
        new,
        history_start=HISTORY_START,
        history_end=HISTORY_END,
    )
    # Weighted mean: (10*2 + 25*2) / 4 = 17.5
    assert combined["logon_count"]["mean"] == pytest.approx(17.5)
    assert combined["logon_count"]["count"] == 4


def test_update_baseline_skips_leakage_in_new_rows():
    existing = {"logon_count": {"mean": 10.0, "std": 0.0, "min": 10.0, "max": 10.0, "count": 1}}
    new = [_row(8, logon_count=999)]  # leakage — must be ignored
    combined = update_baseline(
        existing,
        new,
        history_start=HISTORY_START,
        history_end=HISTORY_END,
    )
    assert combined["logon_count"]["mean"] == 10.0
    assert combined["logon_count"]["count"] == 1
