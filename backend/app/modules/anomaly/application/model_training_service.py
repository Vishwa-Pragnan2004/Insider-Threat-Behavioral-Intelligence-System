"""
ITBIS — Anomaly Module: Model Training Service

Trains an Isolation Forest model on behavioral features and saves
the artifact to disk for use by ModelService during inference.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import structlog
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION

log = structlog.get_logger(__name__)

DEFAULT_OUTPUT_PATH = os.environ.get(
    "ITBIS_MODEL_PATH",
    "./ml_model/itbis_behavior_model_v2.joblib",
)


def _safe_std(v: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 1.0
    if f <= 0.0 or f != f:  # NaN-safe
        return 1.0
    return f


class ModelTrainingService:
    """Trains an Isolation Forest model on behavioral features."""

    def __init__(
        self,
        feature_store,
        output_path: str = DEFAULT_OUTPUT_PATH,
    ) -> None:
        self.feature_store = feature_store
        self.output_path = output_path

    async def train(
        self,
        source_dataset: str = "all",
        window: str = "daily",
        contamination: float = 0.1,
        n_estimators: int = 100,
        random_state: int = 42,
    ) -> dict:
        """Train an Isolation Forest on behavioral features and save the artifact.

        Returns a dict with training summary.
        """
        import datetime as _dt

        feature_rows = await self.feature_store.list_all_features(
            source_dataset=None if source_dataset == "all" else source_dataset,
            window=window,
        )

        if not feature_rows:
            raise ValueError("No feature rows found for training. Ingest data first.")

        feature_rows = [r for r in feature_rows if r.feature_version == FEATURE_VERSION]

        if len(feature_rows) < 10:
            raise ValueError(
                f"Only {len(feature_rows)} feature rows found. Need at least 10 rows to train."
            )

        log.info("anomaly.train.starting", n_rows=len(feature_rows))

        matrix = []
        for row in feature_rows:
            vec = []
            for name in FEATURE_NAMES:
                v = row.features.get(name, 0.0)
                try:
                    vec.append(float(v))
                except (TypeError, ValueError):
                    vec.append(0.0)
            matrix.append(vec)

        X = np.asarray(matrix, dtype=np.float64)

        global_means = {}
        global_stds = {}
        for i, name in enumerate(FEATURE_NAMES):
            col = X[:, i]
            global_means[name] = float(np.mean(col))
            std_val = float(np.std(col))
            global_stds[name] = std_val if std_val > 0 else 1.0

        z_feature_columns = [f"{n}_zscore" for n in FEATURE_NAMES]
        model_features = list(FEATURE_NAMES) + z_feature_columns

        X_32 = np.zeros((len(feature_rows), 32), dtype=np.float64)
        for row_idx, row in enumerate(feature_rows):
            for col_idx, name in enumerate(FEATURE_NAMES):
                X_32[row_idx, col_idx] = X[row_idx, col_idx]
                mean = global_means[name]
                std = global_stds[name]
                z = (X[row_idx, col_idx] - mean) / std if std > 0 else 0.0
                X_32[row_idx, 16 + col_idx] = z

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_32)

        model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
        model.fit(X_scaled)

        scores = model.score_samples(X_scaled)
        score_low = float(np.percentile(scores, 5))
        score_high = float(np.percentile(scores, 95))

        artifact = {
            "model": model,
            "scaler": scaler,
            "baseline_stats": {},
            "global_means": global_means,
            "global_stds": global_stds,
            "feature_columns": list(FEATURE_NAMES),
            "z_feature_columns": z_feature_columns,
            "model_features": model_features,
            "count_features": [],
            "score_low": score_low,
            "score_high": score_high,
            "metadata": {
                "model_version": "itbis_if_v1",
                "feature_version": FEATURE_VERSION,
                "trained_at": _dt.datetime.utcnow().isoformat(),
                "n_training_rows": len(feature_rows),
                "contamination": contamination,
                "n_estimators": n_estimators,
            },
        }

        output_path = Path(self.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            joblib.dump(artifact, str(output_path))

        log.info(
            "anomaly.train.completed",
            path=str(output_path),
            n_rows=len(feature_rows),
            score_low=score_low,
            score_high=score_high,
        )

        return {
            "artifact_path": str(output_path),
            "model_version": artifact["metadata"]["model_version"],
            "feature_version": artifact["metadata"]["feature_version"],
            "n_training_rows": len(feature_rows),
            "score_low": score_low,
            "score_high": score_high,
            "contamination": contamination,
            "n_estimators": n_estimators,
        }
