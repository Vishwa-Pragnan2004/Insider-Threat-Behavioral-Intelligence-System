"""
ITBIS — Anomaly Module: ModelService

Owns the loaded `itbis_behavior_model_v2.joblib` artifact for the
lifetime of the process.  Loads the artifact lazily, validates it
against the Phase 4 feature schema, and exposes the two operations
the rest of the module needs:

  - `prepare_input(features, baseline)` — build the 32-feature vector
    in the model's locked order, applying the scaler, returning
    `(vector_2d, z_scores_dict)`.
  - `score(vector)` — run Isolation Forest and return `(prediction,
    raw_score)`.

The artifact is loaded exactly once per process.  Reloading is
explicit (`reload()`) and intended for tests.
"""
from __future__ import annotations

import os
import threading
import warnings
from dataclasses import dataclass, field
from typing import Any

import joblib  # scikit-learn's joblib — same as pickle but with numpy-aware compression
import structlog

from app.modules.anomaly.domain.exceptions import (
    FeatureIncompatibilityError,
    ModelLoadError,
)
from app.modules.behavioral.domain.enums import FEATURE_NAMES

log = structlog.get_logger(__name__)


# Default artifact path; can be overridden by the env var below.
DEFAULT_ARTIFACT_PATH = os.environ.get(
    "ITBIS_MODEL_PATH",
    "./ml_model/itbis_behavior_model_v2.joblib",
)

REQUIRED_ARTIFACT_KEYS = {
    "model",
    "scaler",
    "baseline_stats",
    "global_means",
    "global_stds",
    "feature_columns",
    "z_feature_columns",
    "model_features",
    "score_low",
    "score_high",
    "metadata",
}


@dataclass
class LoadedArtifact:
    """Container for the loaded model artifact."""

    path: str
    model: Any
    scaler: Any
    baseline_stats: dict[str, dict[str, Any]]
    global_means: dict[str, float]
    global_stds: dict[str, float]
    feature_columns: list[str]
    z_feature_columns: list[str]
    model_features: list[str]
    count_features: list[str]
    score_low: float
    score_high: float
    metadata: dict[str, Any] = field(default_factory=dict)

    # Optional / derived
    model_version: str = "unknown"
    feature_version: str = "unknown"


class ModelService:
    """Loads the anomaly model artifact once and provides inference.

    Thread-safe lazy loading.  The first call to `get_artifact()`
    (transitively from any inference call) triggers the disk load;
    subsequent calls reuse the cached artifact.
    """

    def __init__(self, artifact_path: str = DEFAULT_ARTIFACT_PATH) -> None:
        self.artifact_path = artifact_path
        self._artifact: LoadedArtifact | None = None
        self._lock = threading.Lock()

    # ─── Public API ─────────────────────────────────────────

    def get_artifact(self) -> LoadedArtifact:
        if self._artifact is None:
            with self._lock:
                if self._artifact is None:
                    self._artifact = self._load(self.artifact_path)
        return self._artifact

    def reload(self) -> LoadedArtifact:
        """Force-reload the artifact from disk.  Used by tests."""
        with self._lock:
            self._artifact = self._load(self.artifact_path)
        return self._artifact

    def validate_against_phase4(self) -> None:
        """Cross-check the artifact's expected feature set with Phase 4.

        Raises FeatureIncompatibilityError if the 16 base features are
        missing, in a different order, or contain extra names.  This is
        the canonical compatibility gate; it MUST run before any
        inference.
        """
        art = self.get_artifact()
        if list(art.feature_columns) != list(FEATURE_NAMES):
            raise FeatureIncompatibilityError(
                "Loaded model's feature_columns do not match Phase 4 "
                f"FEATURE_NAMES.\n"
                f"  Phase 4 ({len(FEATURE_NAMES)}): {FEATURE_NAMES}\n"
                f"  Model   ({len(art.feature_columns)}): "
                f"{list(art.feature_columns)}\n"
                "Refusing to run inference.  The .joblib artifact was "
                "trained against a different feature schema."
            )

    # ─── Loading ─────────────────────────────────────────────

    def _load(self, path: str) -> LoadedArtifact:
        if not os.path.exists(path):
            raise ModelLoadError(
                f"Model artifact not found at {path!r}.  Set "
                f"ITBIS_MODEL_PATH or pass artifact_path= explicitly."
            )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pkg = joblib.load(path)
        except Exception as exc:  # noqa: BLE001
            raise ModelLoadError(
                f"Failed to unpickle model artifact at {path!r}: {exc}"
            ) from exc

        missing = REQUIRED_ARTIFACT_KEYS - set(pkg.keys())
        if missing:
            raise ModelLoadError(
                f"Model artifact at {path!r} is missing required keys: "
                f"{sorted(missing)}"
            )

        model = pkg["model"]
        scaler = pkg["scaler"]
        if not callable(getattr(model, "score_samples", None)):
            raise ModelLoadError(
                "Artifact's `model` does not implement score_samples() — "
                "this pipeline requires an Isolation Forest or compatible "
                "anomaly scorer."
            )
        if not callable(getattr(scaler, "transform", None)):
            raise ModelLoadError(
                "Artifact's `scaler` does not implement transform()."
            )

        feature_columns = list(pkg["feature_columns"])
        z_feature_columns = list(pkg["z_feature_columns"])
        model_features = list(pkg["model_features"])
        count_features = list(pkg.get("count_features", []))

        if len(model_features) != len(feature_columns) + len(z_feature_columns):
            raise ModelLoadError(
                f"model_features length ({len(model_features)}) does not equal "
                f"feature_columns + z_feature_columns "
                f"({len(feature_columns) + len(z_feature_columns)})."
            )

        # The 16 z-score columns must align with the 16 base columns by
        # stripping the `_zscore` suffix.
        for base, z in zip(feature_columns, z_feature_columns, strict=False):
            if z != f"{base}_zscore":
                raise ModelLoadError(
                    f"Z-score column name {z!r} does not match base feature "
                    f"{base!r} (expected {base + '_zscore'!r})."
                )

        # The scaler must be fitted on the same 32-feature order.
        scaler_names_raw = getattr(scaler, "feature_names_in_", None)
        scaler_feature_names: list[str] = (
            list(scaler_names_raw) if scaler_names_raw is not None else []
        )
        if scaler_feature_names and scaler_feature_names != model_features:
            raise ModelLoadError(
                "Scaler was fitted on a different feature order than the "
                "model expects.\n"
                f"  scaler.feature_names_in_ (n={len(scaler_feature_names)}): "
                f"{scaler_feature_names[:3]}…\n"
                f"  model_features        (n={len(model_features)}): "
                f"{model_features[:3]}…"
            )

        metadata = dict(pkg.get("metadata", {}) or {})
        artifact = LoadedArtifact(
            path=path,
            model=model,
            scaler=scaler,
            baseline_stats=dict(pkg.get("baseline_stats", {}) or {}),
            global_means=dict(pkg.get("global_means", {}) or {}),
            global_stds=dict(pkg.get("global_stds", {}) or {}),
            feature_columns=feature_columns,
            z_feature_columns=z_feature_columns,
            model_features=model_features,
            count_features=count_features,
            score_low=float(pkg["score_low"]),
            score_high=float(pkg["score_high"]),
            metadata=metadata,
            model_version=str(metadata.get("model_version", "unknown")),
            feature_version=str(metadata.get("feature_version", "unknown")),
        )
        log.info(
            "anomaly.model_loaded",
            path=path,
            model_version=artifact.model_version,
            feature_version=artifact.feature_version,
            n_features=len(artifact.model_features),
            n_estimators=getattr(model, "n_estimators", None),
            contamination=getattr(model, "contamination", None),
        )
        return artifact

    # ─── Inference primitives ───────────────────────────────

    def score(self, matrix: list[list[float]] | Any) -> tuple[int, float]:
        """Run the Isolation Forest and return (prediction, raw_score).

        Prediction is 1 (normal) or -1 (anomaly) per sklearn convention.
        `raw_score` is the output of `score_samples()` — more negative
        is more anomalous.
        """
        art = self.get_artifact()
        # Use DataFrame so the fitted StandardScaler doesn't warn about
        # missing feature names.  Build it in the locked column order.
        import numpy as np
        import pandas as pd

        arr = np.asarray(matrix, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        df = pd.DataFrame(arr, columns=art.model_features)
        scaled = art.scaler.transform(df)
        # sklearn 1.7 prefers ndarray input — feed the underlying array
        score = float(art.model.score_samples(np.asarray(scaled))[0])
        pred = int(art.model.predict(np.asarray(scaled))[0])
        return pred, score
