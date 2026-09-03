"""
ITBIS — Integration test fixtures for the Activity module.

Provides:
  - Per-test in-memory SQLite database (activity tables created fresh)
  - In-memory MongoDB via mongomock-motor
  - Auth helpers: register/login, get user with permissions
  - FastAPI dependency overrides for get_db, get_redis, get_mongo_db
"""
from collections.abc import AsyncGenerator

import fakeredis.aioredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.core.redis_client import get_redis
from app.main import app as fastapi_app
from app.modules.activity.infrastructure.models import (  # noqa: F401
    IngestionErrorModel,
    IngestionJobModel,
)

# Force import of all models so Base.metadata is populated
from app.modules.identity.infrastructure.models import (  # noqa: F401
    AuthAuditLogModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
from app.modules.identity.infrastructure.seeders import seed_identity_module
from app.shared.infrastructure.base_model import Base

# ─── SQLite (Postgres) ───────────────────────────────────────


@pytest_asyncio.fixture
async def db_engine():
    """Fresh in-memory SQLite engine per test, with all tables created."""
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
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )
    async with session_factory() as session:
        await seed_identity_module(session)
        await session.commit()
        yield session
        await session.rollback()


# ─── Redis (fake) ────────────────────────────────────────────


@pytest_asyncio.fixture
async def redis_mock():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


# ─── Mongo (mongomock-motor) ─────────────────────────────────


@pytest_asyncio.fixture
async def mongo_mock_db():
    """In-memory MongoDB database for the duration of one test."""
    client = AsyncMongoMockClient()
    db = client["itbis_events_test"]
    yield db
    client.close()


# ─── FastAPI client with overrides ──────────────────────────


@pytest_asyncio.fixture
async def async_client(
    db_session: AsyncSession,
    redis_mock,
    mongo_mock_db,
) -> AsyncGenerator[AsyncClient, None]:
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

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        yield client

    fastapi_app.dependency_overrides.clear()


# ─── Re-exported session for direct DB access in tests ──────
# Tests that need to manipulate the DB (e.g. promote user role)
# can take this fixture instead of trying to extract the session
# from the dependency override.
@pytest_asyncio.fixture
async def test_db_session(db_session: AsyncSession) -> AsyncSession:
    return db_session


# ─── Auth helpers ────────────────────────────────────────────


VALID_USER = {
    "username": "activity_tester",
    "email": "activity.tester@example.com",
    "password": "SecurePass1!",
    "full_name": "Activity Tester",
}

AUTH_BASE = "/api/v1/auth"
INGESTION_BASE = "/api/v1/ingestion"


async def register_and_login(client: AsyncClient) -> str:
    """Register the default test user and return a valid access token."""
    r = await client.post(f"{AUTH_BASE}/register", json=VALID_USER)
    assert r.status_code == 201, r.text
    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]
