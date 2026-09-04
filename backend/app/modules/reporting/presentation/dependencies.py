"""
ITBIS — Reporting Module: Presentation Dependencies
"""
from functools import wraps

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.presentation.dependencies import get_alert_service
from app.modules.investigations.application.investigation_service import InvestigationService
from app.modules.investigations.presentation.dependencies import get_investigation_service
from app.modules.reporting.application.report_service import ReportService


def get_report_service(
    alert_service: AlertService = Depends(get_alert_service),
    investigation_service: InvestigationService = Depends(get_investigation_service),
) -> ReportService:
    return ReportService(
        alert_service=alert_service,
        investigation_service=investigation_service,
    )
