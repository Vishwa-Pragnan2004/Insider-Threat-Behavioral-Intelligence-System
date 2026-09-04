"""
ITBIS — Reporting Module: Application DTOs
"""
from datetime import datetime

from pydantic import BaseModel, Field


class ReportRequest(BaseModel):
    report_type: str = Field(..., description="Type of report: 'alerts' or 'investigations'")
    start: datetime | None = Field(None, description="Filter start date (ISO-8601)")
    end: datetime | None = Field(None, description="Filter end date (ISO-8601)")
    status: str | None = Field(None, description="Filter by status")
    severity: str | None = Field(None, description="Filter by severity")
    format: str = Field(default="csv", description="Export format: 'csv' or 'json'")


class AlertReportItem(BaseModel):
    id: str
    title: str
    description: str
    severity: str
    status: str
    risk_level: str
    risk_score: float
    user_id: str
    source_dataset: str
    assigned_to: str | None
    investigation_id: str | None
    created_at: datetime
    updated_at: datetime


class InvestigationReportItem(BaseModel):
    id: str
    title: str
    description: str
    severity: str
    status: str
    created_by: str
    assigned_to: str | None
    related_alert_ids: list[str]
    related_user_ids: list[str]
    resolution: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class ReportResponse(BaseModel):
    report_type: str
    generated_at: datetime
    total_count: int
    format: str
