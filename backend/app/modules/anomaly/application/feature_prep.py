"""
ITBIS — Anomaly Module: Feature Preparation

Builds the 32-feature input vector the model expects, in the model's
locked column order, given:

  - a Phase 4 `BehavioralFeatures` row (16 base features)
  - an optional per-user Phase 4 `BehavioralBaseline`
  - the loaded model artifact (for global fallback statistics)

The 16 base features are taken *verbatim* from the Phase 4 row.  The 16
personalised Z-score features are computed as:

    z_i = (value_i - baseline_mean_i) / baseline_std_i

with a safe divide that uses the artifact's global standard deviation
when the per-user `std` is missing, zero, or non-finite.  If no
per-user baseline exists for the user, the artifact's
`global_means` / `global_stds` are used as the fallback (this is the
"baseline_source = 'global'" branch in `AnomalyResult`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.modules.anomaly.application.model_service import LoadedArtifact
from app.modules.behavioral.domain.entities import (
    BehavioralBaseline,
    BehavioralFeatures,
)


@dataclass
class PreparedInput:
    """Result of feature preparation, ready to be scored."""

    # 32-element list, ordered to match the artifact's `model_features`
    vector: list[float]
    # Per-feature Z-scores for explainability and persistence
    zscores: dict[str, float]
    # Mean and std used per feature (for downstream debugging / audit)
    baseline_means: dict[str, float]
    baseline_stds: dict[str, float]
    # Where the baseline came from
    baseline_source: str  # "personal" or "global"


def _safe_std(std: Any) -> float:
    """Return a usable std (never zero / None / NaN)."""
    try:
        v = float(std)
    except (TypeError, ValueError):
        return 0.0
    if v != v or v <= 0.0:  # NaN-safe + non-positive
        return 0.0
    return v


def _lookup_mean(baseline: dict[str, Any], feature: str) -> float | None:
    inner = baseline.get(feature)
    if not isinstance(inner, dict):
        return None
    val = inner.get("mean")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _lookup_std(baseline: dict[str, Any], feature: str) -> float | None:
    inner = baseline.get(feature)
    if not isinstance(inner, dict):
        return None
    val = inner.get("std")
    if val is None:
        return None
    return _safe_std(val)


def build_32_features(
    feature_row: BehavioralFeatures,
    baseline: BehavioralBaseline | None,
    artifact: LoadedArtifact,
) -> PreparedInput:
    """Compose the 32-feature input the model expects.

    Returns a PreparedInput containing the locked-order vector, the
    computed Z-scores (for explainability), and the per-feature
    baseline means/stds that were used.
    """
    # Extract the 16 base feature values from the Phase 4 row.
    # Phase 4 always writes every FEATURE_NAME; missing keys default to 0.0
    # (the Phase 4 aggregator does this — we mirror that here for safety).
    base_values: dict[str, float] = {}
    for name in artifact.feature_columns:
        v = feature_row.features.get(name)
        if v is None:
            v = 0.0
        try:
            base_values[name] = float(v)
        except (TypeError, ValueError):
            base_values[name] = 0.0

    # Choose the baseline source.  Preference order:
    #   1. Per-user baseline (if provided and has all 16 features' mean/std)
    #   2. Artifact's per-user baseline_stats (fallback if Phase 4 has none)
    #   3. Artifact's global_means / global_stds (last resort)
    chosen_stats: dict[str, dict[str, float]] = {}
    baseline_source = "global"

    candidate: dict[str, dict[str, float]] | None = None
    if baseline is not None and baseline.stats:
        candidate = baseline.stats
    elif feature_row.user_id in artifact.baseline_stats:
        candidate = artifact.baseline_stats[feature_row.user_id]

    if candidate is not None:
        # Accept the candidate if it has at least the 16 base features
        # (might be missing the 4 `set_size` features the model doesn't
        # use, that's fine).
        usable = all(
            isinstance(candidate.get(name), dict) and candidate[name].get("mean") is not None
            for name in artifact.feature_columns
        )
        if usable:
            chosen_stats = candidate
            baseline_source = "personal"

    zscores: dict[str, float] = {}
    baseline_means: dict[str, float] = {}
    baseline_stds: dict[str, float] = {}

    for name in artifact.feature_columns:
        if baseline_source == "personal":
            mean = _lookup_mean(chosen_stats, name) or float(artifact.global_means.get(name, 0.0))
            std = _lookup_std(chosen_stats, name)
            if std is None or std == 0.0:
                std = _safe_std(artifact.global_stds.get(name, 0.0))
        else:
            mean = float(artifact.global_means.get(name, 0.0))
            std = _safe_std(artifact.global_stds.get(name, 0.0))
        # Final safety: if std is still zero (degenerate), skip the z-score
        # (return 0.0) — the model can handle a zero deviation column.
        if std == 0.0:
            z = 0.0
        else:
            z = (base_values[name] - mean) / std
        zscores[name] = float(z)
        baseline_means[name] = float(mean)
        baseline_stds[name] = float(std)

    # Build the 32-element vector in the locked model_features order.
    vector: list[float] = []
    for name in artifact.model_features:
        if name in artifact.z_feature_columns:
            base_name = name[: -len("_zscore")]
            vector.append(zscores.get(base_name, 0.0))
        else:
            vector.append(base_values.get(name, 0.0))

    return PreparedInput(
        vector=vector,
        zscores=zscores,
        baseline_means=baseline_means,
        baseline_stds=baseline_stds,
        baseline_source=baseline_source,
    )
