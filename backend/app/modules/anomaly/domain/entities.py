"""
ITBIS — Anomaly Module: Domain Entities
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class BehavioralDeviation:
    """A single top-deviation feature explanation.

    `feature` is the base feature name (without the `_zscore` suffix).
    `zscore` is the signed Z-score; `|zscore|` is what the explainer
    sorts on.  `value` is the current observed feature value, and
    `baseline_mean` / `baseline_std` describe the personal baseline used.
    """

    feature: str
    value: float
    baseline_mean: float
    baseline_std: float
    zscore: float


@dataclass
class AnomalyResult:
    """One row of anomaly detection output for a `(user_id, window, window_start)`.

    Persisted to MongoDB collection `anomaly_results`.
    """

    user_id: str
    source_dataset: str          # "cert" | "win_endpoint" | "all"
    window: str                 # "daily" | "rolling_7d" | "rolling_30d"
    window_start: datetime
    window_end: datetime
    model_version: str          # e.g. "itbis_behavior_v2"
    feature_version: str        # the model's expected feature version

    prediction: AnomalyPrediction
    raw_anomaly_score: float    # Isolation Forest score_samples() output
    risk_score: float           # 0..100 normalised
    risk_level: RiskLevel

    top_behavioral_deviations: list[BehavioralDeviation] = field(default_factory=list)
    # The full 32-feature input vector (in the model's locked order)
    # is preserved for downstream debugging / re-scoring.
    model_input: dict[str, float] = field(default_factory=dict)
    # Identifies which baseline the model actually used for this user
    # ("personal" if a per-user baseline was found, "global" if the
    # artifact's global fallback was used).
    baseline_source: str = "global"

    created_at: datetime = field(default_factory=_utcnow)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
