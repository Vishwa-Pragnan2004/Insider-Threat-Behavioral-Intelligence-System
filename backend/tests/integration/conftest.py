"""
ITBIS — Shared integration-test stack.

Provides the common test stack used by integration tests that have no
module-specific conftest of their own:

  - in-memory SQLite for identity/RBAC + relational models
  - mongomock-motor for event/alert/investigation documents
  - fakeredis for the token store
  - the real identity seeder (roles, permissions, superadmin)

pytest resolves fixtures from the *nearest* conftest first, so module
conftests (activity, alerts, identity) continue to shadow these with their
own variants.  This file is the fallback for modules that don't define one.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.core.redis_client import get_redis
from app.main import app as fastapi_app

# Force-import every model module so Base.metadata is fully populated
# before create_all() runs.
from app.modules.activity.infrastructure.models import (  # noqa: F401
    IngestionErrorModel,
    IngestionJobModel,
)
from app.modules.behavioral.infrastructure.models import (  # noqa: F401
    BehavioralBaselineModel,
)
from app.modules.identity.infrastructure.models import (  # noqa: F401
    AuthAuditLogModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
from app.modules.identity.infrastructure.seeders import seed_identity_module
from app.shared.infrastructure.base_model import Base

# Point the anomaly ModelService at the checked-in artifact.  ModelService
# captures this at import time, so it must be set before app import.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault(
    "ITBIS_MODEL_PATH",
    str(PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v2.joblib"),
)


@pytest_asyncio.fixture
async def db_engine():
    """A fresh in-memory SQLite engine per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """A seeded async SQLite session for a single test."""
    factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )
    async with factory() as session:
        await seed_identity_module(session)
        await session.commit()
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def mongo_mock_db():
    """An in-memory MongoDB stand-in."""
    client = AsyncMongoMockClient()
    db = client["itbis_events_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def redis_mock():
    """A FakeRedis client with decode_responses=True."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def async_client(
    db_session: AsyncSession, redis_mock, mongo_mock_db
) -> AsyncGenerator[AsyncClient, None]:
    """An AsyncClient wired to the isolated SQLite / Mongo / Redis stack."""
    _session = db_session

    async def _get_test_db():
        yield _session

    async def _get_test_redis():
        return redis_mock

    async def _get_test_mongo_db():
        return mongo_mock_db

    fastapi_app.dependency_overrides[get_db] = _get_test_db
    fastapi_app.dependency_overrides[get_redis] = _get_test_redis
    fastapi_app.dependency_overrides[get_mongo_db] = _get_test_mongo_db

    # The alert observer is a process-wide singleton in the anomaly module;
    # reset it so each test gets one bound to this test's mongo_mock_db.
    import app.modules.anomaly.presentation.dependencies as _dep

    _dep._observer_singleton = None

    # ASGITransport does NOT trigger lifespan events — intentional.
    # Seeding happens in db_session instead.
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        yield client

    fastapi_app.dependency_overrides.clear()
