"""
ITBIS — Integration Test Fixtures for Identity Module.
Provides a per-test async HTTP client with:
  - In-memory SQLite database (tables created fresh each test)
  - FakeRedis client
  - Roles/permissions seeded via the real seeder
  - FastAPI dependency overrides applied before each test
"""

import asyncio
from typing import AsyncGenerator

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.main import app as fastapi_app
from app.modules.identity.infrastructure.seeders import seed_identity_module
from app.shared.infrastructure.base_model import Base

# Force import of all models so Base.metadata is populated
from app.modules.identity.infrastructure.models import (  # noqa: F401
    AuthAuditLogModel,
    PermissionModel,
    RoleModel,
    UserModel,
)


@pytest_asyncio.fixture
async def db_engine():
    """Creates a fresh in-memory SQLite engine per test."""
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
    """Provides a seeded async SQLite session for a single test."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )
    async with session_factory() as session:
        # Seed roles/permissions (and superadmin) into test DB
        await seed_identity_module(session)
        await session.commit()
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def redis_mock():
    """Provides a FakeRedis client with decode_responses=True."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession, redis_mock) -> AsyncGenerator[AsyncClient, None]:
    """
    Provides an AsyncClient wired to:
    - An isolated SQLite test database (seeded)
    - A FakeRedis instance
    - FastAPI dependency overrides applied for the duration of the test.
    """
    _session = db_session

    async def _get_test_db():
        yield _session

    async def _get_test_redis():
        return redis_mock

    fastapi_app.dependency_overrides[get_db] = _get_test_db
    fastapi_app.dependency_overrides[get_redis] = _get_test_redis

    # ASGITransport does NOT trigger lifespan events — intentional.
    # We seed via the fixture above instead of lifespan.
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        yield client

    fastapi_app.dependency_overrides.clear()
