"""
ITBIS — Behavioral Module: Baseline Builder

Builds and updates per-user behavioral baselines.

A baseline summarises a user's "normal" behaviour as mean / std / min / max
of each daily feature over a HISTORICAL window that is strictly before
the evaluation period.

CRITICAL: leakage prevention.

    baseline = build_baseline(
        daily_features,             # list of {feature_name: value, ...}
        history_start=...,          # inclusive
        history_end=...,            # EXCLUSIVE — caller MUST set this to
                                    # the start of the evaluation window.
    )

The builder will not silently include any daily feature whose window falls
on or after `history_end`.  This is a defence-in-depth check — the
caller is expected to set the bounds correctly, but the builder will
refuse to leak if they don't.
"""
from __future__ import annotations

import statistics
from datetime import UTC, datetime


def _stats_for(values: list[float]) -> dict[str, float]:
    """Return mean / std / min / max / count for a feature series."""
    if not values:
        return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    mean = statistics.fmean(values)
    if len(values) >= 2:
        std = statistics.pstdev(values) or 0.0
    else:
        std = 0.0
    return {
        "mean": float(mean),
        "std": float(std),
        "min": float(min(values)),
        "max": float(max(values)),
        "count": int(len(values)),
    }


def build_baseline(
    daily_features: list[dict],
    *,
    history_start: datetime,
    history_end: datetime,
) -> dict[str, dict[str, float]]:
    """
    Build a baseline stats dict from a list of daily feature rows.

    Each row is a dict with a "window_start" datetime plus a
    "features" sub-dict (or is itself the feature dict — both supported
    for convenience).

    Returns: {feature_name: {mean, std, min, max, count}}
    """
    if history_start.tzinfo is None:
        history_start = history_start.replace(tzinfo=UTC)
    if history_end.tzinfo is None:
        history_end = history_end.replace(tzinfo=UTC)
    if not (history_start < history_end):
        raise ValueError(
            "history_start must be strictly less than history_end (exclusive)"
        )

    # Defensive leakage check: a row is eligible only if its entire window
    # falls within [history_start, history_end).  Any overlap with the
    # evaluation period [history_end, +∞) is rejected.  This is the
    # primary guard against future-data leakage.
    eligible: list[dict] = []
    for row in daily_features:
        row_start = _row_window_start(row)
        if row_start is None:
            continue
        if row_start.tzinfo is None:
            row_start = row_start.replace(tzinfo=UTC)
        row_end = _row_window_end(row) or row_start
        if row_end.tzinfo is None:
            row_end = row_end.replace(tzinfo=UTC)
        if row_end <= history_start:
            continue
        if row_start >= history_end:
            # Row starts in the evaluation period — leakage.
            continue
        if row_end > history_end:
            # Row straddles the boundary — leakage.
            continue
        eligible.append(row)

    if not eligible:
        return {}

    # Collect per-feature value series.
    feature_values: dict[str, list[float]] = {}
    for row in eligible:
        feats = row.get("features") if "features" in row else row
        for name, value in feats.items():
            if not isinstance(value, int | float):
                continue
            feature_values.setdefault(name, []).append(float(value))

    return {name: _stats_for(values) for name, values in feature_values.items()}


def update_baseline(
    existing: dict[str, dict[str, float]] | None,
    new_daily_features: list[dict],
    *,
    history_start: datetime,
    history_end: datetime,
) -> dict[str, dict[str, float]]:
    """
    Update an existing baseline with new daily features.

    The same leakage rules as `build_baseline` apply.
    """
    new_stats = build_baseline(
        new_daily_features,
        history_start=history_start,
        history_end=history_end,
    )
    if not existing:
        return new_stats

    # Combine: per feature, average the means and stds weighted by count.
    combined: dict[str, dict[str, float]] = {}
    feature_names = set(existing.keys()) | set(new_stats.keys())
    for name in feature_names:
        prev = existing.get(name, {"mean": 0.0, "std": 0.0, "count": 0})
        curr = new_stats.get(name, {"mean": 0.0, "std": 0.0, "count": 0})
        total_count = int(prev["count"]) + int(curr["count"])
        if total_count == 0:
            combined[name] = {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "count": 0}
            continue
        # Weighted mean
        weighted_mean = (
            (float(prev["mean"]) * int(prev["count"]) + float(curr["mean"]) * int(curr["count"]))
            / total_count
        )
        # Combine variances (population) approximately
        prev_var = float(prev.get("std", 0.0)) ** 2
        curr_var = float(curr.get("std", 0.0)) ** 2
        combined_var = (
            (prev_var * max(int(prev["count"]) - 1, 0) + curr_var * max(int(curr["count"]) - 1, 0))
            / max(total_count - 1, 1)
        ) if total_count >= 2 else 0.0
        combined[name] = {
            "mean": float(weighted_mean),
            "std": float(combined_var ** 0.5),
            "min": min(
                float(prev.get("min", weighted_mean)),
                float(curr.get("min", weighted_mean)),
            ),
            "max": max(
                float(prev.get("max", weighted_mean)),
                float(curr.get("max", weighted_mean)),
            ),
            "count": total_count,
        }
    return combined


# ─── helpers ────────────────────────────────────────────────


def _row_window_start(row: dict) -> datetime | None:
    if "window_start" in row:
        return row["window_start"]
    feats = row.get("features") if isinstance(row.get("features"), dict) else None
    if feats and "window_start" in feats:
        return feats["window_start"]
    return None


def _row_window_end(row: dict) -> datetime | None:
    if "window_end" in row:
        return row["window_end"]
    feats = row.get("features") if isinstance(row.get("features"), dict) else None
    if feats and "window_end" in feats:
        return feats["window_end"]
    return None
