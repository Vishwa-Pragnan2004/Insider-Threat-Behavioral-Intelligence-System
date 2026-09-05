"""
ITBIS — Investigations Module: Application DTOs
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ─── Investigation ────────────────────────────────────────


class InvestigationCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    description: str = Field(default="", max_length=5000)
    severity: str = Field(default="MEDIUM", description="LOW | MEDIUM | HIGH | CRITICAL")
    related_alert_ids: list[uuid.UUID] = Field(default_factory=list)
    related_user_ids: list[str] = Field(default_factory=list)
    assigned_to: str | None = None


class InvestigationAssignRequest(BaseModel):
    user_id: str = Field(..., min_length=1)


class InvestigationStatusRequest(BaseModel):
    status: str = Field(..., description="Target status (validated for transitions)")
    resolution: str | None = Field(
        default=None,
        description="Optional resolution text.  Usually set when closing.",
    )


class InvestigationAddAlertRequest(BaseModel):
    alert_id: uuid.UUID
    user_id: str | None = Field(
        default=None,
        description="Optional user id of the alert's owner — added to related_user_ids.",
    )


class InvestigationResponse(BaseModel):
    id: str
    title: str
    description: str
    severity: str
    status: str
    created_by: str
    assigned_to: str | None = None
    related_alert_ids: list[str] = Field(default_factory=list)
    related_user_ids: list[str] = Field(default_factory=list)
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    notes: list["NoteResponse"] = Field(default_factory=list)


class InvestigationListResponse(BaseModel):
    investigations: list[InvestigationResponse] = Field(default_factory=list)
    count: int
    total: int
    skip: int
    limit: int


# ─── Note ──────────────────────────────────────────────────


class NoteCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000)


class NoteResponse(BaseModel):
    id: str
    investigation_id: str
    author_id: str
    content: str
    created_at: datetime


class NoteListResponse(BaseModel):
    investigation_id: str
    notes: list[NoteResponse] = Field(default_factory=list)
    count: int
