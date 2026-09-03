"""
ITBIS — Anomaly Module: Explainability

Given the per-feature Z-scores computed in `feature_prep`, return the
top-N features ranked by absolute Z-score.  These are the "top
behavioral deviations" persisted with every AnomalyResult and
surfaced in the API.
"""
from __future__ import annotations

from app.modules.anomaly.domain.entities import BehavioralDeviation


def top_deviations(
    zscores: dict[str, float],
    baseline_means: dict[str, float],
    baseline_stds: dict[str, float],
    observed_values: dict[str, float],
    *,
    top_n: int = 3,
) -> list[BehavioralDeviation]:
    """Return the top-N most-deviating features by |Z-score|.

    Ties are broken by alphabetical order of the feature name so the
    output is deterministic.
    """
    items: list[BehavioralDeviation] = []
    for name in sorted(zscores.keys()):
        z = zscores[name]
        items.append(
            BehavioralDeviation(
                feature=name,
                value=float(observed_values.get(name, 0.0)),
                baseline_mean=float(baseline_means.get(name, 0.0)),
                baseline_std=float(baseline_stds.get(name, 0.0)),
                zscore=float(z),
            )
        )
    items.sort(key=lambda d: (-abs(d.zscore), d.feature))
    return items[:top_n]


def format_deviation_line(dev: BehavioralDeviation) -> str:
    """Human-readable one-liner for an alert or report."""
    return f"{dev.feature} ({dev.zscore:+.1f}σ)"
