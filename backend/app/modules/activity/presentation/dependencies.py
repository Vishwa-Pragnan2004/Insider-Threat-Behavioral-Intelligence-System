"""
ITBIS — Activity Module: FastAPI Dependencies
"""
# ruff: noqa: B008  # FastAPI's Depends() in defaults is the documented pattern

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.activity.application.services.ingestion_service import IngestionService
from app.modules.activity.infrastructure.mongo_event_store import MongoActivityEventStore
from app.modules.activity.infrastructure.repositories import (
    SQLIngestionErrorRepository,
    SQLIngestionJobRepository,
)


def get_activity_event_store(
    db: AsyncIOMotorDatabase = Depends(get_mongo_db),
) -> MongoActivityEventStore:
    """Provide a MongoDB-backed activity event store."""
    return MongoActivityEventStore(db)


def get_ingestion_service(
    session: AsyncSession = Depends(get_db),
    event_store: MongoActivityEventStore = Depends(get_activity_event_store),
) -> IngestionService:
    """Provide an IngestionService wired with Postgres + Mongo repos."""
    job_repo = SQLIngestionJobRepository(session)
    error_repo = SQLIngestionErrorRepository(session)
    return IngestionService(
        job_repo=job_repo,
        error_repo=error_repo,
        event_store=event_store,
    )
