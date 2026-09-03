"""
ITBIS — Integration tests for the Phase 5 training export endpoint.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.behavioral.infrastructure.models import (  # noqa: F401
    BehavioralBaselineModel,
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

# ─── Test stack (mirrors tests/integration/behavioral/test_api.py) ───


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
    "username": "ml_user",
    "email": "ml@example.com",
    "password": "SecurePass1!",
    "full_name": "ML User",
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


def _feature_doc(
    *,
    user_id: str = "alice",
    window: str = "daily",
    window_start: datetime,
    window_end: datetime,
    source_dataset: str = "cert",
    features: dict | None = None,
    event_count: int = 1,
) -> dict:
    return {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "window": window,
        "window_start": window_start,
        "window_end": window_end,
        "source_dataset": source_dataset,
        "feature_version": FEATURE_VERSION,
        "features": features
        or {name: float(i + 1) for i, name in enumerate(FEATURE_NAMES)},
        "event_count": event_count,
        "generated_at": datetime(2026, 8, 1, tzinfo=UTC),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ─── Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_requires_auth(async_client: AsyncClient):
    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/export",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_export_end_to_end(
    async_client: AsyncClient, db_session, mongo_mock_db, tmp_path
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed 3 days of features for 2 users
    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    docs = []
    for u in ("alice", "bob"):
        for d in range(3):
            docs.append(
                _feature_doc(
                    user_id=u,
                    window_start=_aware(base + timedelta(days=d)),
                    window_end=_aware(base + timedelta(days=d + 1)),
                )
            )
    await mongo_mock_db["behavioral_features"].insert_many(docs)

    output_dir = str(tmp_path / "training_export")
    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/export",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-04T00:00:00+00:00",
            "output_dir": output_dir,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count"] == 6
    assert body["user_count"] == 2
    assert body["window_count"] == 3
    assert body["feature_version"] == FEATURE_VERSION
    assert body["column_order"][:7] == [
        "user_id",
        "window",
        "window_start",
        "window_end",
        "source_dataset",
        "feature_version",
        "event_count",
    ]
    assert body["column_order"][7:] == FEATURE_NAMES

    # files exist
    csv_path = Path(body["features_csv_path"])
    manifest_path = Path(body["manifest_path"])
    assert csv_path.exists()
    assert manifest_path.exists()

    # CSV header is locked
    csv_text = csv_path.read_text(encoding="utf-8").splitlines()
    header = csv_text[0].split(",")
    assert header[7:] == FEATURE_NAMES
    assert len(csv_text) == 7  # 1 header + 6 data rows

    # Manifest documents the contract
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["feature_version"] == FEATURE_VERSION
    assert manifest["row_count"] == 6
    assert manifest["ml_feature_columns"] == FEATURE_NAMES
    assert manifest["missing_value_policy"] == "filled_with_zero"


@pytest.mark.asyncio
async def test_export_respects_source_dataset_filter(
    async_client: AsyncClient, db_session, mongo_mock_db, tmp_path
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    await mongo_mock_db["behavioral_features"].insert_many(
        [
            _feature_doc(
                user_id="alice",
                source_dataset="cert",
                window_start=_aware(base),
                window_end=_aware(base + timedelta(days=1)),
            ),
            _feature_doc(
                user_id="alice",
                source_dataset="win_endpoint",
                window_start=_aware(base),
                window_end=_aware(base + timedelta(days=1)),
            ),
        ]
    )

    output_dir = str(tmp_path / "export_cert")
    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/export",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
            "source_dataset": "cert",
            "output_dir": output_dir,
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 1
    assert body["source_dataset"] == "cert"


@pytest.mark.asyncio
async def test_export_handles_no_features_gracefully(
    async_client: AsyncClient, db_session, tmp_path
):
    token = await _make_admin_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    output_dir = str(tmp_path / "export_empty")
    r = await async_client.post(
        f"{BEHAVIORAL_BASE}/export",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
            "output_dir": output_dir,
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] == 0
    # Header-only CSV still written
    csv_text = Path(body["features_csv_path"]).read_text(encoding="utf-8")
    lines = [line for line in csv_text.splitlines() if line]
    assert len(lines) == 1  # header only
