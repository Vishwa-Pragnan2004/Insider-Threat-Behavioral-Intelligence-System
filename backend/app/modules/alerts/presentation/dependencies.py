"""
ITBIS — Alerts Module: FastAPI Dependencies
"""
# ruff: noqa: B008
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.alerts.application.alert_generation_service import (
    AlertGenerationService,
)
from app.modules.alerts.application.alert_service import AlertService
from app.modules.alerts.application.policy import DEFAULT_POLICY
from app.modules.alerts.domain.repositories import IUserDirectory
from app.modules.alerts.infrastructure.mongo_alert_repository import (
    MongoAlertRepository,
)
from app.modules.alerts.infrastructure.sql_user_directory import SqlUserDirectory
from app.modules.anomaly.domain.repositories import IAnomalyResultStore
from app.modules.anomaly.infrastructure.mongo_result_store import (
    MongoAnomalyResultStore,
)

log = structlog.get_logger(__name__)


def get_alert_repo(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> MongoAlertRepository:
    return MongoAlertRepository(db)


def get_anomaly_repo_for_alerts(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> IAnomalyResultStore:
    """
    Re-use the Phase-5 Mongo store as the alerts module's read
    source for anomaly_results.  The alerts module depends on the
    anomaly module's *interface* (IAnomalyResultStore) — not its
    concrete implementation — so the dependency arrow is
    alerts → anomaly (one-way).
    """
    return MongoAnomalyResultStore(db)


def get_user_directory(
    session: AsyncSession = Depends(get_db),
) -> IUserDirectory:
    """SQL-backed implementation of IUserDirectory (for assignment validation)."""
    return SqlUserDirectory(session)


def get_alert_generation_service(
    alert_repo: MongoAlertRepository = Depends(get_alert_repo),
    anomaly_repo: IAnomalyResultStore = Depends(get_anomaly_repo_for_alerts),
) -> AlertGenerationService:
    return AlertGenerationService(
        alert_repo=alert_repo, anomaly_repo=anomaly_repo, policy=DEFAULT_POLICY
    )


def get_alert_service(
    alert_repo: MongoAlertRepository = Depends(get_alert_repo),
    user_directory: IUserDirectory = Depends(get_user_directory),
) -> AlertService:
    return AlertService(alert_repo=alert_repo, user_directory=user_directory)


# ─── Observer factory (Phase-5 → Phase-6 hook) ──────────────


def make_alert_observer(
    service: AlertGenerationService,
) -> Callable[..., Awaitable[None]]:
    """
    Build the observer callable the Phase-5 anomaly service will
    invoke after each successful persistence.  The anomaly
    presentation/dependencies module imports this and passes it
    to AnomalyDetectionService(..., alert_observer=observer).
    """

    async def observer(anomaly) -> None:  # type: ignore[no-untyped-def]
        try:
            await service.generate_for_anomaly(anomaly)
        except Exception:  # noqa: BLE001
            # An alert-generation failure must NOT fail the
            # anomaly-detection request.  Log and swallow.
            log.exception(
                "alerts.observer_failed",
                anomaly_id=str(getattr(anomaly, "id", "?")),
                user_id=getattr(anomaly, "user_id", "?"),
            )

    return observer
