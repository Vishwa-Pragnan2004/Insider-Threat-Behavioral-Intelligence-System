"""
ITBIS — Reporting Module: Report Generation Service
"""
import csv
import io
from datetime import datetime

from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.investigations.application.investigation_service import InvestigationService
from app.modules.investigations.domain.enums import InvestigationStatus


class ReportService:
    def __init__(
        self,
        alert_service: AlertService,
        investigation_service: InvestigationService,
    ):
        self._alert_service = alert_service
        self._investigation_service = investigation_service

    async def generate_alerts_csv(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
        severity: str | None = None,
    ) -> tuple[str, list[dict]]:
        status_enum = AlertStatus(status) if status else None
        severity_enum = AlertSeverity(severity) if severity else None
        
        alerts, total = await self._alert_service.list(
            status=status_enum,
            severity=severity_enum,
            start=start,
            end=end,
            skip=0,
            limit=10000,
        )
        rows = []
        for a in alerts:
            rows.append({
                "id": str(a.id),
                "title": a.title,
                "description": a.description,
                "severity": a.severity.value if hasattr(a.severity, 'value') else str(a.severity),
                "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
                "risk_level": a.risk_level,
                "risk_score": a.risk_score,
                "user_id": a.user_id,
                "source_dataset": a.source_dataset,
                "assigned_to": a.assigned_to or "",
                "investigation_id": str(a.investigation_id) if a.investigation_id else "",
                "created_at": a.created_at.isoformat() if a.created_at else "",
                "updated_at": a.updated_at.isoformat() if a.updated_at else "",
            })
        return self._to_csv(rows), rows

    async def generate_investigations_csv(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        status: str | None = None,
    ) -> tuple[str, list[dict]]:
        status_enum = InvestigationStatus(status) if status else None
        
        investigations, total = await self._investigation_service.list(
            status=status_enum,
            skip=0,
            limit=10000,
        )
        rows = []
        for inv in investigations:
            rows.append({
                "id": str(inv.id),
                "title": inv.title,
                "description": inv.description,
                "severity": inv.severity,
                "status": inv.status.value if hasattr(inv.status, 'value') else str(inv.status),
                "created_by": inv.created_by,
                "assigned_to": inv.assigned_to or "",
                "related_alert_ids": ",".join(str(a) for a in inv.related_alert_ids),
                "related_user_ids": ",".join(str(u) for u in inv.related_user_ids),
                "resolution": inv.resolution or "",
                "created_at": inv.created_at.isoformat() if inv.created_at else "",
                "updated_at": inv.updated_at.isoformat() if inv.updated_at else "",
                "closed_at": inv.closed_at.isoformat() if inv.closed_at else "",
            })
        return self._to_csv(rows), rows

    def _to_csv(self, rows: list[dict]) -> str:
        if not rows:
            return ""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue()
