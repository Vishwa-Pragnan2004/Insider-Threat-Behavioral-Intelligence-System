"""
ITBIS — Dashboards API

    GET /api/v1/dashboards/analyst   Security Analyst workspace   (dashboard:analyst)
    GET /api/v1/dashboards/soc       SOC operations               (dashboard:soc)
    GET /api/v1/dashboards/manager   Security Manager risk posture (dashboard:manager)

Responses are plain JSON aggregates; see DashboardService for how each figure
is derived.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.dashboards.application.dashboard_service import DashboardService
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import require_permission
from app.modules.ueba.application.detection_pipeline import pipeline_coordinator

router = APIRouter()


def _service(mongo_db: Any, session: AsyncSession) -> DashboardService:
    return DashboardService(mongo_db, session, pipeline_status=pipeline_coordinator.status)


@router.get("/analyst", summary="Security Analyst dashboard")
async def analyst_dashboard(
    viewer: User = Depends(require_permission(PermissionName.DASHBOARD_ANALYST)),
    mongo_db: Any = Depends(get_mongo_db),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await _service(mongo_db, session).analyst(viewer_id=str(viewer.id))


@router.get(
    "/soc",
    summary="SOC operations dashboard",
    dependencies=[Depends(require_permission(PermissionName.DASHBOARD_SOC))],
)
async def soc_dashboard(
    mongo_db: Any = Depends(get_mongo_db),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await _service(mongo_db, session).soc()


@router.get(
    "/manager",
    summary="Security Manager dashboard",
    dependencies=[Depends(require_permission(PermissionName.DASHBOARD_MANAGER))],
)
async def manager_dashboard(
    mongo_db: Any = Depends(get_mongo_db),
    session: AsyncSession = Depends(get_db),
) -> dict:
    return await _service(mongo_db, session).manager()
