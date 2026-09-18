"""
ITBIS — Feedback Module: FastAPI dependencies
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.presentation.dependencies import get_alert_service
from app.modules.feedback.application.verdict_service import VerdictService
from app.modules.feedback.infrastructure.repository import SqlVerdictRepository


def get_verdict_service(
    session: AsyncSession = Depends(get_db),
    alerts: AlertService = Depends(get_alert_service),
) -> VerdictService:
    return VerdictService(SqlVerdictRepository(session), alerts)
