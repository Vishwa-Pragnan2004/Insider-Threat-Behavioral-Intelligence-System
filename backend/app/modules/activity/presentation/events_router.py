"""
ITBIS — Activity Module: event browsing API

    GET /api/v1/activity/events           page through canonical events, newest first
    GET /api/v1/activity/events/summary   counts for the last N hours

Agent telemetry and CERT uploads were stored but nothing exposed them, so
collected logs never appeared in the UI. Both endpoints need behavioral:read.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.mongo_client import get_mongo_db
from app.modules.activity.application.event_queries import EventFilters, EventQueries
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import require_permission

router = APIRouter()


class ActivityEventOut(BaseModel):
    id: str
    event_id: str | None
    event_type: str
    timestamp: str | None
    user_id: str
    device_id: str | None
    device_name: str | None
    source_dataset: str
    target_resource: str | None
    target_type: str | None
    action: str | None
    result: str | None
    ip_address: str | None
    is_remote: bool | None
    risk_indicators: list[str]
    tags: list[str]
    enrichments: dict[str, Any] | None
    ingested_at: str | None


class ActivityEventListOut(BaseModel):
    events: list[ActivityEventOut]
    total: int
    skip: int
    limit: int


class UserCount(BaseModel):
    user_id: str
    count: int


class HourCount(BaseModel):
    hour: str
    count: int


class ActivitySummaryOut(BaseModel):
    window_hours: int
    total: int
    flagged: int
    active_users: int
    active_devices: int
    by_event_type: dict[str, int]
    by_source: dict[str, int]
    top_users: list[UserCount]
    hourly: list[HourCount]


@router.get(
    "/events",
    response_model=ActivityEventListOut,
    summary="Browse collected activity events",
    dependencies=[Depends(require_permission(PermissionName.BEHAVIORAL_READ))],
)
async def list_events(
    user_id: str | None = Query(None, max_length=255),
    event_type: str | None = Query(None, max_length=64),
    source_dataset: str | None = Query(None, max_length=64),
    device_id: str | None = Query(None, max_length=255),
    start: datetime | None = None,
    end: datetime | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    mongo_db: Any = Depends(get_mongo_db),
) -> ActivityEventListOut:
    filters = EventFilters(
        user_id=user_id,
        event_type=event_type,
        source_dataset=source_dataset,
        device_id=device_id,
        start=start,
        end=end,
    )
    events, total = await EventQueries(mongo_db).list_events(filters, skip=skip, limit=limit)
    return ActivityEventListOut(
        events=[ActivityEventOut(**e) for e in events], total=total, skip=skip, limit=limit
    )


@router.get(
    "/events/summary",
    response_model=ActivitySummaryOut,
    summary="Activity counts for the last N hours",
    dependencies=[Depends(require_permission(PermissionName.BEHAVIORAL_READ))],
)
async def events_summary(
    hours: int = Query(24, ge=1, le=720),
    mongo_db: Any = Depends(get_mongo_db),
) -> ActivitySummaryOut:
    return ActivitySummaryOut(**await EventQueries(mongo_db).summary(hours=hours))
