"""
ITBIS — Anomaly Module: Application DTOs
"""
from datetime import datetime

from pydantic import BaseModel, Field

# ─── Request DTOs ─────────────────────────────────────────


class AnomalyDetectRequest(BaseModel):
    """POST /api/v1/anomaly/detect"""

    user_id: str | None = Field(
        default=None,
        description="If omitted, detection runs for every user with features in the window.",
    )
    start: datetime
    end: datetime
    source_dataset: str = Field(default="all")
    window: str = Field(default="daily")


class TrainRequest(BaseModel):
    """POST /api/v1/anomaly/train"""

    source_dataset: str = Field(default="all")
    window: str = Field(default="daily")
    contamination: float = Field(default=0.1, description="Isolation Forest contamination parameter")
    n_estimators: int = Field(default=100, description="Number of Isolation Forest trees")


# ─── Response DTOs ─────────────────────────────────────────


class BehavioralDeviationResponse(BaseModel):
    feature: str
    value: float
    baseline_mean: float
    baseline_std: float
    zscore: float


class AnomalyResultResponse(BaseModel):
    id: str
    user_id: str
    source_dataset: str
    window: str
    window_start: datetime
    window_end: datetime
    model_version: str
    feature_version: str
    prediction: str
    raw_anomaly_score: float
    risk_score: float
    risk_level: str
    baseline_source: str
    top_behavioral_deviations: list[BehavioralDeviationResponse] = Field(default_factory=list)
    created_at: datetime


class AnomalyDetectResponse(BaseModel):
    """Summary of a detect run."""

    results: list[AnomalyResultResponse] = Field(default_factory=list)
    count: int
    risk_levels: dict[str, int] = Field(default_factory=dict)


class AnomalyResultListResponse(BaseModel):
    results: list[AnomalyResultResponse] = Field(default_factory=list)
    count: int


class ModelInfoResponse(BaseModel):
    """Metadata about the loaded anomaly model."""

    artifact_path: str
    model_version: str
    feature_version: str
    feature_columns: list[str] = Field(default_factory=list)
    z_feature_columns: list[str] = Field(default_factory=list)
    model_features: list[str] = Field(default_factory=list)
    n_features: int
    score_low: float
    score_high: float
    phase4_feature_compatible: bool
