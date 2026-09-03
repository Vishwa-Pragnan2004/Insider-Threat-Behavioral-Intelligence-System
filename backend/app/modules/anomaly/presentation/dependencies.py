"""
ITBIS — Anomaly Module: FastAPI Dependencies
"""
# ruff: noqa: B008
import os
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.anomaly.application.anomaly_detection_service import (
    AnomalyDetectionService,
)
from app.modules.anomaly.application.model_service import (
    DEFAULT_ARTIFACT_PATH,
    ModelService,
)
from app.modules.anomaly.domain.entities import AnomalyResult
from app.modules.anomaly.infrastructure.mongo_result_store import (
    MongoAnomalyResultStore,
)
from app.modules.behavioral.infrastructure.repositories import (
    MongoBehavioralFeatureStore,
    SQLBehavioralBaselineRepository,
)

# Process-wide model service (loads artifact lazily, once)
_model_service: ModelService | None = None


def get_model_service() -> ModelService:
    global _model_service
    if _model_service is None:
        # Allow env var to override the default location
        path = os.environ.get("ITBIS_MODEL_PATH", DEFAULT_ARTIFACT_PATH)
        _model_service = ModelService(artifact_path=path)
    return _model_service


def get_result_store(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> MongoAnomalyResultStore:
    return MongoAnomalyResultStore(db)


def get_feature_store(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> MongoBehavioralFeatureStore:
    return MongoBehavioralFeatureStore(db)


def get_baseline_repo(
    session: AsyncSession = Depends(get_db),
) -> SQLBehavioralBaselineRepository:
    return SQLBehavioralBaselineRepository(session)


# ─── Phase 6 alert observer hook ───────────────────────────
#
# Pattern: build the alert observer inside the FastAPI dependency
# chain so the MongoDB override is honored.  The observer is
# constructed per-request (cheap closure over the resolved DB
# handle) so test isolation is preserved.

log = structlog.get_logger(__name__)


async def _build_observer(
    db: Any,
) -> Callable[[AnomalyResult], Awaitable[None]] | None:
    """Build an observer using an already-resolved MongoDB handle."""
    try:
        from app.modules.alerts.application.alert_generation_service import (
            AlertGenerationService,
        )
        from app.modules.alerts.application.policy import DEFAULT_POLICY
        from app.modules.alerts.infrastructure.mongo_alert_repository import (
            MongoAlertRepository,
        )
        from app.modules.anomaly.infrastructure.mongo_result_store import (
            MongoAnomalyResultStore,
        )
    except Exception as exc:  # noqa: BLE001
        log.info("anomaly.observer.unavailable", reason=str(exc))
        return None

    alert_repo = MongoAlertRepository(db)
    anomaly_repo = MongoAnomalyResultStore(db)
    service = AlertGenerationService(
        alert_repo=alert_repo,
        anomaly_repo=anomaly_repo,
        policy=DEFAULT_POLICY,
    )

    async def observer(anomaly: AnomalyResult) -> None:
        try:
            await service.generate_for_anomaly(anomaly)
        except Exception:  # noqa: BLE001
            log.exception(
                "anomaly.observer.failed",
                anomaly_id=str(anomaly.id),
                user_id=anomaly.user_id,
            )

    return observer


async def get_alert_observer(
    db: Any = Depends(get_mongo_db),
) -> Callable[[AnomalyResult], Awaitable[None]] | None:
    """FastAPI dependency: returns the per-request alert observer."""
    return await _build_observer(db)


def get_anomaly_detection_service(
    model_service: ModelService = Depends(get_model_service),
    feature_store: MongoBehavioralFeatureStore = Depends(get_feature_store),
    baseline_repo: SQLBehavioralBaselineRepository = Depends(get_baseline_repo),
    result_store: MongoAnomalyResultStore = Depends(get_result_store),
    alert_observer: Callable[[AnomalyResult], Awaitable[None]] | None = Depends(
        get_alert_observer
    ),
) -> AnomalyDetectionService:
    return AnomalyDetectionService(
        model_service=model_service,
        feature_store=feature_store,
        baseline_repo=baseline_repo,
        result_store=result_store,
        alert_observer=alert_observer,
    )
