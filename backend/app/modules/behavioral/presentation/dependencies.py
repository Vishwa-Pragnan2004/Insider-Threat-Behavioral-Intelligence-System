"""
ITBIS — Behavioral Module: FastAPI Dependencies
"""
# ruff: noqa: B008  # FastAPI Depends() in defaults is the documented pattern
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.activity.infrastructure.mongo_event_store import (
    MongoActivityEventStore,
)
from app.modules.behavioral.application.services.feature_engineering_service import (
    FeatureEngineeringService,
)
from app.modules.behavioral.infrastructure.repositories import (
    MongoBehavioralFeatureStore,
    SQLBehavioralBaselineRepository,
)


def get_feature_store(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> MongoBehavioralFeatureStore:
    return MongoBehavioralFeatureStore(db)


def get_event_source(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> MongoActivityEventStore:
    """Reuse the activity store as the event source for the behavioral
    pipeline.  Phase 4 only needs the read API (`find_events`)."""
    return MongoActivityEventStore(db)


def get_baseline_repo(
    session: AsyncSession = Depends(get_db),
) -> SQLBehavioralBaselineRepository:
    return SQLBehavioralBaselineRepository(session)


def get_feature_engineering_service(
    feature_store: MongoBehavioralFeatureStore = Depends(get_feature_store),
    baseline_repo: SQLBehavioralBaselineRepository = Depends(get_baseline_repo),
    event_source: MongoActivityEventStore = Depends(get_event_source),
) -> FeatureEngineeringService:
    return FeatureEngineeringService(
        feature_store=feature_store,
        baseline_repo=baseline_repo,
        event_source=event_source,
    )
