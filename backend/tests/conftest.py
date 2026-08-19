"""
ITBIS — Test Configuration & Shared Fixtures
pytest conftest.py — automatically loaded by pytest for all tests.
"""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from app.main import app as fastapi_app
from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis_client import get_redis
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import RoleName
from app.shared.infrastructure.base_model import Base
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
import fakeredis.aioredis


# ─── Event Loop ─────────────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Use a single event loop for all async tests in the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ─── Test Settings Override ─────────────────────────────────
@pytest.fixture(scope="session")
def test_settings():
    """Return settings configured for the test environment."""
    settings = get_settings()
    return settings


# ─── HTTP Test Client ────────────────────────────────────────
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP test client for the FastAPI application.
    Use this fixture in all API endpoint tests.
    """
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as ac:
        yield ac


# ─── Application Fixture ─────────────────────────────────────
@pytest.fixture(scope="session")
def app() -> FastAPI:
    """Return the FastAPI application instance."""
    return fastapi_app


# ─── Database Fixture ────────────────────────────────────────
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provides an in-memory SQLite database session for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# ─── Redis Fixture ───────────────────────────────────────────
@pytest_asyncio.fixture
async def redis_mock():
    """Provides a FakeRedis client."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


# ─── App Overrides ───────────────────────────────────────────
@pytest.fixture(autouse=True)
def override_dependencies(app: FastAPI, db_session: AsyncSession, redis_mock):
    """Override FastAPI dependencies with test fixtures."""
    async def _get_test_db():
        yield db_session

    async def _get_test_redis():
        return redis_mock

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_redis] = _get_test_redis
    yield
    app.dependency_overrides.clear()


# ─── Auth Headers Helper ─────────────────────────────────────
@pytest.fixture
def auth_headers():
    """Returns a factory function to generate auth headers for a specific user ID."""
    def _create_headers(user_id: str, roles: list[str] = None, permissions: list[str] = None, is_superadmin: bool = False):
        claims = {
            "roles": roles or [RoleName.VIEWER.value],
            "permissions": permissions or [],
            "is_superadmin": is_superadmin,
        }
        token = token_service.create_access_token(user_id, claims)
        return {"Authorization": f"Bearer {token}"}
    return _create_headers
