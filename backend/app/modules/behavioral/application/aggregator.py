"""
ITBIS — Behavioral Module: Feature Aggregator

Given a list of CanonicalEvent documents (as Mongo dicts) for a single
user, produces a flat dict of feature values keyed by
`FEATURE_DEFINITIONS` names.

The aggregator is deliberately:
  - pure (no I/O, no global state)
  - deterministic (same events → same features)
  - extensible (new features = new FeatureDefinition entry)

The feature *names* and *semantics* are the wire contract with the
eventual ML training pipeline; see module docstring in `features.py`.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from app.modules.behavioral.application.features import (
    FEATURE_DEFINITIONS,
    event_field,
    feature_names,
)


def aggregate_features(events: list[dict]) -> dict[str, float]:
    """
    Aggregate a list of canonical event dicts into a feature row.

    Returns a dict keyed by every name in `FEATURE_DEFINITIONS`, with
    numeric values (int or float).  Missing features default to 0.
    """
    features: dict[str, float] = {name: 0.0 for name in feature_names()}

    # Pre-compute aggregations that need a set view.
    set_fields: dict[str, set] = {}
    for name, defn in FEATURE_DEFINITIONS.items():
        if defn.aggregator == "set_size" and defn.field is not None:
            set_fields[name] = set()

    for ev in events:
        for name, defn in FEATURE_DEFINITIONS.items():
            agg = defn.aggregator
            if agg == "count":
                features[name] += 1
            elif agg == "event_match":
                if defn.event_match and defn.event_match(ev):
                    features[name] += 1
            elif agg == "set_size":
                value = event_field(ev, defn.field) if defn.field else None
                if value is not None:
                    set_fields[name].add(value)

    for name, values in set_fields.items():
        features[name] = float(len(values))

    return features


def aggregate_empty_row() -> dict[str, float]:
    """Return a feature row for a user with no events in the window."""
    return {name: 0.0 for name in feature_names()}


def normalise_window(
    window_start: datetime, window_end: datetime
) -> tuple[datetime, datetime]:
    """
    Ensure a window is in UTC and that start < end.

    Accepts naive datetimes (assumed UTC).  Returns timezone-aware UTC values.
    """
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=UTC)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=UTC)
    if not (window_start < window_end):
        raise ValueError(
            f"window_start ({window_start}) must be < window_end ({window_end})"
        )
    return window_start, window_end


_ONE_DAY = timedelta(days=1)


def iter_daily_windows(
    window_start: datetime, window_end: datetime
) -> Iterable[tuple[datetime, datetime]]:
    """
    Yield successive [day_start, day_end) UTC windows between the bounds.

    Both bounds are assumed UTC.  Day boundaries are 00:00 UTC.
    """
    window_start, window_end = normalise_window(window_start, window_end)
    cur = window_start
    while cur < window_end:
        if cur.hour or cur.minute or cur.second or cur.microsecond:
            next_day = datetime(
                cur.year, cur.month, cur.day, tzinfo=UTC
            ) + _ONE_DAY
        else:
            next_day = cur + _ONE_DAY
        nxt = min(next_day, window_end)
        yield cur, nxt
        cur = nxt
