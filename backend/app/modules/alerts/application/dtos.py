"""
ITBIS — Alerts Module: Application DTOs
"""
from datetime import datetime

from pydantic import BaseModel, Field

# ─── AlertDeviation ────────────────────────────────────────


class AlertDeviationDTO(BaseModel):
    feature: str
    value: float
    baseline_mean: float
    baseline_std: float
    zscore: float


# ─── Alert entity responses ─────────────────────────────────


class AlertResponse(BaseModel):
    id: str
    idempotency_key: str
    anomaly_result_id: str
    user_id: str
    source_dataset: str
    window: str
    window_start: datetime
    window_end: datetime
    model_version: str
    feature_version: str
    title: str
    description: str
    risk_score: float
    risk_level: str
    severity: str
    status: str
    assigned_to: str | None = None
    investigation_id: str | None = None
    top_behavioral_deviations: list[AlertDeviationDTO] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse] = Field(default_factory=list)
    count: int
    total: int
    skip: int
    limit: int


# ─── Request DTOs ───────────────────────────────────────────


class AlertAssignRequest(BaseModel):
    user_id: str = Field(..., min_length=1, description="ID of the user to assign the alert to.")


class AlertStatusUpdateRequest(BaseModel):
    status: str = Field(
        ...,
        description="New status.  Must be a valid lifecycle transition from the current status.",
    )


class AlertGenerateRequest(BaseModel):
    """
    POST /api/v1/alerts/generate — manually trigger alert generation
    from existing anomaly results.
    """

    start: datetime | None = None
    end: datetime | None = None
    user_id: str | None = None
    risk_level: str | None = None
    source_dataset: str | None = None
    limit: int = Field(
        default=1000,
        ge=1,
        le=10_000,
        description="Maximum number of anomaly results to process.",
    )


class AlertGenerateResponse(BaseModel):
    """Response for POST /alerts/generate."""

    created: int
    skipped_duplicates: int
    skipped_below_threshold: int
    total_processed: int
