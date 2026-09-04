"""
ITBIS — Integration tests: Windows Endpoint Agent → server

These tests:
  - stand up the FastAPI app with in-memory SQLite + mongomock + FakeRedis
  - drive the agent's Uploader directly (no real Windows collectors)
  - assert the server accepts the batch, dedupes, and stores canonical events

The full server test stack (identity seed, auth, mongo, etc.) lives in
tests/integration/activity/conftest.py. We reuse its fixtures.

NOTE: These tests require the `itbis_agent` package which is a separate
Windows endpoint agent. They will be skipped if the package is not installed.
"""
from __future__ import annotations

import sys

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
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
from app.modules.identity.domain.enums import RoleName

# Force-import models so Base.metadata is populated
from app.modules.identity.infrastructure.models import (  # noqa: F401
    AuthAuditLogModel,
    PermissionModel,
    RoleModel,
    UserModel,
)
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from app.modules.identity.infrastructure.seeders import seed_identity_module
from app.shared.infrastructure.base_model import Base

# ─── Test stack (mirrors tests/integration/activity/conftest.py) ───


@pytest_asyncio.fixture
async def db_engine():
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
    client = AsyncMongoMockClient()
    db = client["itbis_events_test"]
    yield db
    client.close()


@pytest_asyncio.fixture
async def redis_mock():
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def async_client(db_session, redis_mock, mongo_mock_db) -> AsyncGenerator[AsyncClient, None]:
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


# ─── Auth helpers ─────────────────────────────────────────────


VALID_AGENT_USER = {
    "username": "agentops",
    "email": "agentops@example.com",
    "password": "SecurePass1!",
    "full_name": "Agent Ops",
}

AUTH_BASE = "/api/v1/auth"


async def _make_agent_token(client: AsyncClient, db_session: AsyncSession) -> str:
    """Register, promote to ADMIN, log in, return access token."""
    r = await client.post(f"{AUTH_BASE}/register", json=VALID_AGENT_USER)
    assert r.status_code == 201, r.text
    user_repo = SQLUserRepository(db_session)
    role_repo = SQLRoleRepository(db_session)
    user = await user_repo.get_by_email(VALID_AGENT_USER["email"])
    admin_role = await role_repo.get_by_name(RoleName.ADMIN)
    user._is_superadmin = True
    user.assign_role(admin_role)
    await user_repo.save(user)
    await db_session.commit()

    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": VALID_AGENT_USER["email"], "password": VALID_AGENT_USER["password"]},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ─── Tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_events_endpoint_requires_auth(async_client: AsyncClient):
    r = await async_client.post("/api/v1/ingestion/events", json={
        "agent_id": "WS-DEV-001",
        "events": [
            {
                "event_type": "logon",
                "source_dataset": "win_endpoint",
                "timestamp": "2026-08-30T08:00:00+00:00",
                "user_id": "alice",
            }
        ],
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_agent_uploader_posts_to_server(async_client, db_session, mongo_mock_db):
    """Full agent path: queue -> uploader -> POST /events -> Mongo.

    The uploader is a sync component; this test exercises the same wire
    format by posting an EventBatch envelope via the test's async client.
    """
    pytest.importorskip("itbis_agent")
    from itbis_agent.schemas import CanonicalEvent, EventBatch, EventType

    token = await _make_agent_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    events = [
        CanonicalEvent(
            event_id=uuid.uuid4(),
            event_type=EventType.LOGON,
            source_dataset="win_endpoint",
            raw_event_id=f"4624-{i}",
            timestamp=datetime.now(UTC),
            user_id="DOMAIN\\alice",
            device_id="WS-DEV-001",
        )
        for i in range(3)
    ]
    batch = EventBatch(agent_id="WS-DEV-001", events=events)

    r = await async_client.post(
        "/api/v1/ingestion/events",
        json=batch.model_dump(mode="json"),
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 3
    assert body["duplicates"] == 0
    assert body["rejected"] == 0

    # Verify the events made it into Mongo
    count = await mongo_mock_db["canonical_events"].count_documents({})
    assert count == 3
    docs = await mongo_mock_db["canonical_events"].find({}).to_list(length=10)
    assert all(d["agent_id"] == "WS-DEV-001" for d in docs)
    assert all(d["job_id"] == "agent:WS-DEV-001" for d in docs)


@pytest.mark.asyncio
async def test_server_dedupes_duplicate_events(async_client, db_session, mongo_mock_db):
    pytest.importorskip("itbis_agent")
    from itbis_agent.schemas import CanonicalEvent, EventBatch, EventType

    token = await _make_agent_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Build a batch with two events sharing the same raw_event_id
    ev = CanonicalEvent(
        event_id=uuid.uuid4(),
        event_type=EventType.LOGON,
        source_dataset="win_endpoint",
        raw_event_id="4624-same",
        timestamp=datetime.now(UTC),
        user_id="DOMAIN\\alice",
        device_id="WS-DEV-001",
    )
    ev_dup = ev.model_copy(update={"event_id": uuid.uuid4()})
    batch = EventBatch(agent_id="WS-DEV-001", events=[ev, ev_dup])

    r = await async_client.post(
        "/api/v1/ingestion/events",
        json=batch.model_dump(mode="json"),
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 1
    assert body["duplicates"] == 1
    assert body["rejected"] == 0

    # Only one event in Mongo
    count = await mongo_mock_db["canonical_events"].count_documents({})
    assert count == 1


@pytest.mark.asyncio
async def test_full_queue_to_server_flow(async_client, db_session, mongo_mock_db):
    """Drive the full agent pipeline (queue enqueue -> batch -> POST)."""
    pytest.importorskip("itbis_agent")
    import os
    import tempfile

    from itbis_agent.config import QueueConfig
    from itbis_agent.queue import PersistentQueue
    from itbis_agent.schemas import CanonicalEvent, EventBatch, EventType

    token = await _make_agent_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    tmpdir = tempfile.mkdtemp()
    queue = PersistentQueue(
        QueueConfig(db_path=os.path.join(tmpdir, "q.db"), max_pending_events=1000),
        agent_id="WS-DEV-001",
    )
    try:
        for i in range(5):
            ev = CanonicalEvent(
                event_id=uuid.uuid4(),
                event_type=EventType.LOGON,
                source_dataset="win_endpoint",
                raw_event_id=f"flow-{i}",
                timestamp=datetime.now(UTC),
                user_id="DOMAIN\\bob",
                device_id="WS-DEV-001",
            )
            assert queue.enqueue(ev) is True

        # Peek and post in one batch
        queued = queue.peek(limit=10)
        batch = EventBatch(
            agent_id="WS-DEV-001",
            events=[q.event for q in queued],
        )
        r = await async_client.post(
            "/api/v1/ingestion/events",
            json=batch.model_dump(mode="json"),
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["accepted"] == 5

        # Mark them sent
        queue.mark_sent([q.id for q in queued])
        assert queue.count_pending() == 0
    finally:
        queue.close()


@pytest.mark.asyncio
async def test_server_rejects_oversized_batch(async_client, db_session):
    """The server caps a batch at 1000 events (DoS guard)."""
    token = await _make_agent_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    big_batch = {
        "agent_id": "WS-DEV-001",
        "events": [
            {
                "event_type": "logon",
                "source_dataset": "win_endpoint",
                "timestamp": "2026-08-30T08:00:00+00:00",
                "user_id": f"u{i}",
            }
            for i in range(1001)
        ],
    }
    r = await async_client.post(
        "/api/v1/ingestion/events", json=big_batch, headers=headers
    )
    assert r.status_code == 422  # pydantic validation


@pytest.mark.asyncio
async def test_endpoint_requires_agent_ingest_permission(async_client, db_session):
    """A VIEWER user must not be able to POST to /events."""

    # Register a plain user (gets VIEWER role by default).
    r = await async_client.post(f"{AUTH_BASE}/register", json={
        "username": "plainviewer",
        "email": "viewer@example.com",
        "password": "SecurePass1!",
        "full_name": "Plain Viewer",
    })
    assert r.status_code == 201
    r = await async_client.post(f"{AUTH_BASE}/login", json={
        "email": "viewer@example.com", "password": "SecurePass1!"
    })
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        "/api/v1/ingestion/events",
        json={
            "agent_id": "WS-DEV-001",
            "events": [{
                "event_type": "logon",
                "source_dataset": "win_endpoint",
                "timestamp": "2026-08-30T08:00:00+00:00",
                "user_id": "u1",
            }],
        },
        headers=headers,
    )
    # VIEWER has alerts:read but not agent:ingest
    assert r.status_code == 403
