"""
ITBIS — Behavioral Module: Application DTOs
"""
from datetime import datetime

from pydantic import BaseModel, Field


class FeatureGenerationRequest(BaseModel):
    """Request payload for POST /api/v1/behavioral/generate."""

    start: datetime
    end: datetime
    source_dataset: str = Field(default="all", description="'cert' | 'win_endpoint' | 'all'")
    user_ids: list[str] | None = None
    window: str = Field(default="daily", description="'daily' | 'rolling_7d' | 'rolling_30d'")


class FeatureGenerationResponse(BaseModel):
    """Summary of a feature generation run."""

    rows_generated: int
    users_processed: int
    feature_version: str
    start: datetime
    end: datetime
    source_dataset: str
    window: str


class BehavioralFeatureRow(BaseModel):
    """Single feature row returned to clients."""

    id: str
    user_id: str
    window: str
    window_start: datetime
    window_end: datetime
    source_dataset: str
    feature_version: str
    event_count: int
    features: dict[str, float]


class BehavioralFeatureListResponse(BaseModel):
    user_id: str
    rows: list[BehavioralFeatureRow] = Field(default_factory=list)
    count: int
    feature_version: str


class BehavioralProfileResponse(BaseModel):
    """The user-level baseline profile returned to clients."""

    user_id: str
    feature_version: str
    observation_days: int
    window_start: datetime
    window_end: datetime
    source_dataset: str
    stats: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="{feature_name: {mean, std, min, max, count}}",
    )
    updated_at: datetime | None = None


# ─── Phase 5: training dataset export ─────────────────────


class TrainingExportRequest(BaseModel):
    """Request payload for POST /api/v1/behavioral/export."""

    start: datetime
    end: datetime
    source_dataset: str = Field(
        default="all", description="'cert' | 'win_endpoint' | 'all'"
    )
    window: str = Field(
        default="daily", description="'daily' | 'rolling_7d' | 'rolling_30d'"
    )
    output_dir: str = Field(
        default="./itbis_training_export",
        description="Filesystem path for the exported CSV + manifest.",
    )


class TrainingExportResponse(BaseModel):
    """Response payload describing a completed export."""

    row_count: int
    user_count: int
    window_count: int
    feature_version: str
    start: datetime
    end: datetime
    source_dataset: str
    window: str
    manifest_path: str
    features_csv_path: str
    column_order: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
