"""
ITBIS — Reporting Module: API Router

Endpoints (all under /api/v1/reports):

  GET  /alerts/export        export alerts as CSV
  GET  /investigations/export export investigations as CSV

Permission map:
  reports:read  -> GET endpoints
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import require_permission
from app.modules.reporting.application.dtos import ReportRequest
from app.modules.reporting.application.report_service import ReportService
from app.modules.reporting.presentation.dependencies import get_report_service


router = APIRouter()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@router.get(
    "/alerts/export",
    summary="Export alerts as CSV",
    dependencies=[Depends(require_permission(PermissionName.REPORTS_READ))],
)
async def export_alerts_csv(
    start: str | None = Query(None, description="ISO-8601 UTC start date"),
    end: str | None = Query(None, description="ISO-8601 UTC end date"),
    status: str | None = Query(None, description="Filter by alert status"),
    severity: str | None = Query(None, description="Filter by severity"),
    service: ReportService = Depends(get_report_service),
):
    csv_content, _ = await service.generate_alerts_csv(
        start=_parse_dt(start),
        end=_parse_dt(end),
        status=status,
        severity=severity,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=alerts_report.csv"
        },
    )


@router.get(
    "/investigations/export",
    summary="Export investigations as CSV",
    dependencies=[Depends(require_permission(PermissionName.REPORTS_READ))],
)
async def export_investigations_csv(
    start: str | None = Query(None, description="ISO-8601 UTC start date"),
    end: str | None = Query(None, description="ISO-8601 UTC end date"),
    status: str | None = Query(None, description="Filter by investigation status"),
    service: ReportService = Depends(get_report_service),
):
    csv_content, _ = await service.generate_investigations_csv(
        start=_parse_dt(start),
        end=_parse_dt(end),
        status=status,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=investigations_report.csv"
        },
    )
