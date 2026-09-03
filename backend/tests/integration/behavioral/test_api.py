"""
ITBIS — Integration tests for the behavioral features API.

Covers:
  - generate features (POST /behavioral/generate)
  - list features  (GET  /behavioral/features)
  - get profile    (GET  /behavioral/profile/{user_id})
  - auth + RBAC
  - data flow: ingest → feature row visible via GET /features
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

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

# ─── Test stack ────────────────────────────────────────────


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
async def async_client(
    db_session, redis_mock, mongo_mock_db
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


# ─── Auth helpers ──────────────────────────────────────────


VALID_USER = {
    "username": "behavior_user",
    "email": "behavior@example.com",
    "password": "SecurePass1!",
    "full_name": "Behavior User",
}

AUTH_BASE = "/api/v1/auth"
BEHAVIORAL_BASE = "/api/v1/behavioral"


async def _make_admin_token(client: AsyncClient, db_session: AsyncSession) -> str:
    r = await client.post(f"{AUTH_BASE}/register", json=VALID_USER)
    assert r.status_code == 201, r.text
    user_repo = SQLUserRepository(db_session)
    role_repo = SQLRoleRepository(db_session)
    user = await user_repo.get_by_email(VALID_USER["email"])
    admin_role = await role_repo.get_by_name(RoleName.ADMIN)
    user._is_superadmin = True
    user.assign_role(admin_role)
    await user_repo.save(user)
    await db_session.commit()
    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": VALID_USER["email"], "password": VALID_USER["password"]},
    )
    return r.json()["access_token"]


async def _make_viewer_token(client: AsyncClient) -> str:
    """Register a second user (gets VIEWER by default)."""
    payload = {**VALID_USER, "username": "viewer_user", "email": "viewer@example.com"}
    r = await client.post(f"{AUTH_BASE}/register", json=payload)
    assert r.status_code == 201
    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    return r.json()["access_token"]


# ─── Seed helpers ──────────────────────────────────────────


def _canon_event_dict(
    *,
    event_id: uuid.UUID | None = None,
    event_type: str,
    timestamp: datetime,
    user_id: str = "alice",
    source_dataset: str = "cert",
    device_id: str | None = "WS-1",
    target_resource: str | None = None,
    risk_indicators: list[str] | None = None,
) -> dict:
    """Build a canonical event doc matching the shape stored by Phase 2
    (timestamps as ISO strings, as produced by `model_dump(mode='json')`)."""
    ev: dict = {
        "_id": str(event_id or uuid.uuid4()),
        "event_type": event_type,
        "source_dataset": source_dataset,
        "timestamp": timestamp.isoformat(),
        "user_id": user_id,
    }
    if device_id is not None:
        ev["device_id"] = device_id
    if target_resource is not None:
        ev["target_resource"] = target_resource
    if risk_indicators is not None:
        ev["risk_indicators"] = risk_indicators
    return ev


# ─── Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoints_require_auth(async_client: AsyncClient):
    r = await async_client.post(f"{BEHAVIORAL_BASE}/generate", json={})
    assert r.status_code == 401
    r = await async_client.get(f"{BEHAVIORAL_BASE}/features?user_id=alice")
    assert r.status_code == 401
    r = await async_client.get(f"{BEHAVIORAL_BASE}/profile/alice")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generate_requires_create_permission(
    async_client: AsyncClient, db_session
):
    """A VIEWER can read but cannot create features."""
    viewer_token = await _make_viewer_token(async_client)
    headers = {"Authorization": f"Bearer {viewer_token}"}
    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/generate",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
        headers=headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_generate_features_end_to_end(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    """End-to-end: seed events → POST /generate → rows in Mongo."""
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 3 days of events
    base = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    for d in range(3):
        await mongo_mock_db["canonical_events"].insert_one(
            _canon_event_dict(
                event_type="logon", timestamp=base + timedelta(days=d)
            )
        )
        await mongo_mock_db["canonical_events"].insert_one(
            _canon_event_dict(
                event_type="file_read",
                timestamp=base + timedelta(days=d, hours=2),
                target_resource=f"/etc/file{d}.txt",
            )
        )

    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/generate",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-04T00:00:00+00:00",
            "source_dataset": "cert",
        },
        headers=headers,
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["rows_generated"] == 3
    assert body["users_processed"] == 1
    assert body["feature_version"] == "behavioral_features_v1"
    assert body["source_dataset"] == "cert"

    # Verify rows in Mongo
    feat_count = await mongo_mock_db["behavioral_features"].count_documents({})
    assert feat_count == 3


@pytest.mark.asyncio
async def test_generate_features_handles_empty_dataset(
    async_client: AsyncClient, db_session
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/generate",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-04T00:00:00+00:00",
        },
        headers=headers,
    )
    assert r.status_code == 202
    body = r.json()
    assert body["rows_generated"] == 0
    assert body["users_processed"] == 0


@pytest.mark.asyncio
async def test_generate_features_handles_agent_and_cert_via_all(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    """The same user has both CERT and agent events — 'all' sees both."""
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    await mongo_mock_db["canonical_events"].insert_one(
        _canon_event_dict(
            event_type="logon", timestamp=base, source_dataset="cert"
        )
    )
    await mongo_mock_db["canonical_events"].insert_one(
        _canon_event_dict(
            event_type="app_launch",
            timestamp=base,
            source_dataset="win_endpoint",
            device_id="WS-AGENT",
        )
    )

    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/generate",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
            "source_dataset": "all",
        },
        headers=headers,
    )
    assert r.status_code == 202
    body = r.json()
    assert body["rows_generated"] == 1
    assert body["source_dataset"] == "all"

    # The single row should reflect both events
    doc = await mongo_mock_db["behavioral_features"].find_one({})
    assert doc is not None
    assert doc["features"]["logon_count"] == 1
    assert doc["features"]["process_activity_count"] == 1


@pytest.mark.asyncio
async def test_list_features_returns_user_rows(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    for d in range(2):
        await mongo_mock_db["canonical_events"].insert_one(
            _canon_event_dict(
                event_type="logon", timestamp=base + timedelta(days=d)
            )
        )

    r1 = await async_client.post(
        f"{BEHAVIORAL_BASE}/generate",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-03T00:00:00+00:00",
        },
        headers=headers,
    )
    assert r1.status_code == 202

    r2 = await async_client.get(
        f"{BEHAVIORAL_BASE}/features",
        params={"user_id": "alice"},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["user_id"] == "alice"
    assert body["count"] == 2
    assert body["feature_version"] == "behavioral_features_v1"
    for row in body["rows"]:
        assert "logon_count" in row["features"]
        assert "external_email_count" in row["features"]


@pytest.mark.asyncio
async def test_get_profile_returns_baseline(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 7 days of history ending TODAY (within the 30-day trailing window)
    now = datetime.now(UTC).replace(microsecond=0)
    history_start = now - timedelta(days=7)
    for d in range(7):
        await mongo_mock_db["canonical_events"].insert_one(
            _canon_event_dict(
                event_type="logon",
                timestamp=history_start + timedelta(days=d, hours=9),
            )
        )

    r = await async_client.get(
        f"{BEHAVIORAL_BASE}/profile/alice",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == "alice"
    assert body["observation_days"] >= 1
    assert "logon_count" in body["stats"]
    # 7 events spread over a 30-day window — mean should be > 0 (some
    # observation days have activity).
    assert body["stats"]["logon_count"]["mean"] > 0
    assert body["stats"]["logon_count"]["max"] >= 1.0
    assert body["stats"]["logon_count"]["count"] >= 1


@pytest.mark.asyncio
async def test_get_profile_returns_404_for_unknown_user(
    async_client: AsyncClient, db_session
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.get(f"{BEHAVIORAL_BASE}/profile/ghost-user", headers=headers)
    assert r.status_code == 404
