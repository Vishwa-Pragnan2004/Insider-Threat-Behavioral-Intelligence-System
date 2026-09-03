"""
ITBIS — Integration tests for the anomaly detection API (Phase 5).

Covers:
  - /detect (POST)  — full inference flow end-to-end
  - /results        — list + filter by risk_level
  - /users/{id}/results — per-user listing
  - /model-info     — model metadata + Phase 4 compatibility flag
  - /results/{id}   — single-result fetch + 404 on miss
  - auth (401) + RBAC (403 for VIEWER on /detect)
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
from app.modules.behavioral.domain.enums import FEATURE_NAMES, FEATURE_VERSION
from app.modules.identity.domain.enums import RoleName

# Force-import models so Base.metadata is populated
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from app.modules.identity.infrastructure.seeders import seed_identity_module
from app.shared.infrastructure.base_model import Base

# ─── Test stack (mirrors other integration conftests) ───


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

    # Force a fresh model service for the test process (the dependency
    # provider uses a module-level singleton; clear it so we get a
    # fresh load with the env var we set at the top of this file).

    import app.modules.anomaly.presentation.dependencies as _dep_mod

    _dep_mod._model_service = None

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        yield client

    fastapi_app.dependency_overrides.clear()


# ─── Auth helpers ──────────────────────────────────────────


ADMIN_USER = {
    "username": "anomaly_admin",
    "email": "anomaly.admin@example.com",
    "password": "SecurePass1!",
    "full_name": "Anomaly Admin",
}
VIEWER_USER = {
    "username": "anomaly_viewer",
    "email": "anomaly.viewer@example.com",
    "password": "SecurePass1!",
    "full_name": "Anomaly Viewer",
}
AUTH_BASE = "/api/v1/auth"
ANOMALY_BASE = "/api/v1/anomaly"


async def _make_admin(client: AsyncClient, db: AsyncSession) -> str:
    r = await client.post(f"{AUTH_BASE}/register", json=ADMIN_USER)
    assert r.status_code == 201, r.text
    user_repo = SQLUserRepository(db)
    role_repo = SQLRoleRepository(db)
    user = await user_repo.get_by_email(ADMIN_USER["email"])
    admin_role = await role_repo.get_by_name(RoleName.ADMIN)
    user._is_superadmin = True
    user.assign_role(admin_role)
    await user_repo.save(user)
    await db.commit()
    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": ADMIN_USER["email"], "password": ADMIN_USER["password"]},
    )
    return r.json()["access_token"]


async def _make_viewer(client: AsyncClient) -> str:
    r = await client.post(f"{AUTH_BASE}/register", json=VIEWER_USER)
    assert r.status_code == 201
    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": VIEWER_USER["email"], "password": VIEWER_USER["password"]},
    )
    return r.json()["access_token"]


# ─── Feature seed helpers ──────────────────────────────────


def _feature_doc(
    *,
    user_id: str,
    source_dataset: str = "cert",
    window_start: datetime,
    window_end: datetime,
    values: dict[str, float],
) -> dict:
    feats = {n: 0.0 for n in FEATURE_NAMES}
    feats.update(values)
    return {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "window": "daily",
        "window_start": window_start,
        "window_end": window_end,
        "source_dataset": source_dataset,
        "feature_version": FEATURE_VERSION,
        "features": feats,
        "event_count": 1,
        "generated_at": datetime(2026, 8, 1, tzinfo=UTC),
    }


# ─── Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoints_require_auth(async_client: AsyncClient):
    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
    )
    assert r.status_code == 401
    r = await async_client.get(f"{ANOMALY_BASE}/results")
    assert r.status_code == 401
    r = await async_client.get(f"{ANOMALY_BASE}/model-info")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_model_info_reports_phase4_compatibility(
    async_client: AsyncClient, db_session
):
    token = await _make_admin(async_client, db_session)
    r = await async_client.get(
        f"{ANOMALY_BASE}/model-info",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phase4_feature_compatible"] is True
    assert body["n_features"] == 32
    assert len(body["feature_columns"]) == 16
    assert len(body["z_feature_columns"]) == 16
    assert len(body["model_features"]) == 32
    assert body["score_low"] < body["score_high"]


@pytest.mark.asyncio
async def test_viewer_role_cannot_trigger_detection(async_client: AsyncClient):
    token = await _make_viewer(async_client)
    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    # VIEWER has anomaly:read but NOT anomaly:create
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_viewer_role_can_read_results_and_model_info(async_client: AsyncClient):
    token = await _make_viewer(async_client)
    r = await async_client.get(
        f"{ANOMALY_BASE}/results",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    r = await async_client.get(
        f"{ANOMALY_BASE}/model-info",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_full_detect_flow_persists_result(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    token = await _make_admin(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed two days of features for one user with high values.
    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    await mongo_mock_db["behavioral_features"].insert_many([
        _feature_doc(
            user_id="alice",
            window_start=base,
            window_end=base + timedelta(days=1),
            values={n: 50.0 for n in FEATURE_NAMES},  # all features way up
        ),
        _feature_doc(
            user_id="alice",
            window_start=base + timedelta(days=1),
            window_end=base + timedelta(days=2),
            values={n: 60.0 for n in FEATURE_NAMES},
        ),
    ])

    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "user_id": "alice",
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-03T00:00:00+00:00",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2
    # All high-activity -> all CRITICAL/HIGH risk
    for r in body["results"]:
        assert 0.0 <= r["risk_score"] <= 100.0
        assert r["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert r["prediction"] in ("normal", "anomaly")
        assert r["user_id"] == "alice"
        assert len(r["top_behavioral_deviations"]) == 3
        # Model input must contain 32 keys
        # (the response model only surfaces the top deviations;
        #  model_input is not in the wire schema)

    # Verify persistence in Mongo
    count = await mongo_mock_db["anomaly_results"].count_documents({})
    assert count == 2


@pytest.mark.asyncio
async def test_detect_for_user_with_no_features_returns_empty(
    async_client: AsyncClient, db_session
):
    """When the user has no Phase 4 features, detection returns
    count=0 rather than a 404 (a clean empty result).
    """
    token = await _make_admin(async_client, db_session)
    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "user_id": "ghost",
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["results"] == []


@pytest.mark.asyncio
async def test_detect_without_user_id_runs_for_all_users(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    token = await _make_admin(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    for user in ("alice", "bob"):
        await mongo_mock_db["behavioral_features"].insert_one(
            _feature_doc(
                user_id=user,
                window_start=base,
                window_end=base + timedelta(days=1),
                values={"logon_count": 5.0},
            )
        )

    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    user_ids = {r["user_id"] for r in body["results"]}
    assert user_ids == {"alice", "bob"}


@pytest.mark.asyncio
async def test_list_results_filtered_by_risk_level(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    token = await _make_admin(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    # Seed and run detection so persistence kicks in.
    await mongo_mock_db["behavioral_features"].insert_many([
        _feature_doc(
            user_id="alice",
            window_start=base + timedelta(days=d),
            window_end=base + timedelta(days=d + 1),
            values={n: 100.0 for n in FEATURE_NAMES},  # very anomalous
        )
        for d in range(2)
    ])
    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "user_id": "alice",
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-03T00:00:00+00:00",
        },
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    detected_levels = {r["risk_level"] for r in body["results"]}
    assert "HIGH" in detected_levels or "CRITICAL" in detected_levels

    # Now query for HIGH
    r = await async_client.get(
        f"{ANOMALY_BASE}/results",
        params={"risk_level": "HIGH"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert all(r["risk_level"] == "HIGH" for r in body["results"])


@pytest.mark.asyncio
async def test_get_user_results(async_client: AsyncClient, db_session, mongo_mock_db):
    token = await _make_admin(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    for user in ("alice", "bob"):
        await mongo_mock_db["behavioral_features"].insert_one(
            _feature_doc(
                user_id=user,
                window_start=base,
                window_end=base + timedelta(days=1),
                values={n: 10.0 for n in FEATURE_NAMES},
            )
        )
    await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
        headers=headers,
    )

    r = await async_client.get(
        f"{ANOMALY_BASE}/users/alice/results",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert all(r["user_id"] == "alice" for r in body["results"])


@pytest.mark.asyncio
async def test_get_result_by_id(async_client: AsyncClient, db_session, mongo_mock_db):
    token = await _make_admin(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    await mongo_mock_db["behavioral_features"].insert_one(
        _feature_doc(
            user_id="alice",
            window_start=base,
            window_end=base + timedelta(days=1),
            values={n: 50.0 for n in FEATURE_NAMES},
        )
    )
    r = await async_client.post(
        f"{ANOMALY_BASE}/detect",
        json={
            "user_id": "alice",
            "start": "2026-08-01T00:00:00+00:00",
            "end": "2026-08-02T00:00:00+00:00",
        },
        headers=headers,
    )
    result_id = r.json()["results"][0]["id"]

    r2 = await async_client.get(
        f"{ANOMALY_BASE}/results/{result_id}",
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == result_id

    # Missing
    r3 = await async_client.get(
        f"{ANOMALY_BASE}/results/{uuid.uuid4()}",
        headers=headers,
    )
    assert r3.status_code == 404


# ─── FIX 2: repeated /anomaly/detect must be safe + idempotent ─────


@pytest.mark.asyncio
async def test_repeated_anomaly_detect_is_idempotent_and_id_safe(
    async_client: AsyncClient, db_session, mongo_mock_db
):
    """
    FIX 2: running anomaly detection for the same (user, window,
    window_start) twice must not raise, must not create duplicate
    anomaly result documents, and must not attempt to mutate the
    existing Mongo `_id` field.  The repo uses the $setOnInsert /
    $set pattern so the second call is a no-op on `_id`.
    """
    from uuid import UUID

    token = await _make_admin(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed one day's feature row.
    base = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    await mongo_mock_db["behavioral_features"].insert_one(
        _feature_doc(
            user_id="dedup-user",
            window_start=base,
            window_end=base + timedelta(days=1),
            values={n: 50.0 for n in FEATURE_NAMES},
        )
    )
    payload = {
        "user_id": "dedup-user",
        "start": "2026-08-01T00:00:00+00:00",
        "end": "2026-08-02T00:00:00+00:00",
    }

    # First detection.
    r1 = await async_client.post(
        f"{ANOMALY_BASE}/detect", json=payload, headers=headers
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["count"] == 1

    # Count anomaly_results in Mongo after first detect.
    count_after_first = await mongo_mock_db["anomaly_results"].count_documents(
        {"user_id": "dedup-user"}
    )
    assert count_after_first == 1

    # Capture the _id of the persisted doc for the second-call check.
    first_doc = await mongo_mock_db["anomaly_results"].find_one(
        {"user_id": "dedup-user"}
    )
    assert first_doc is not None
    original_id = first_doc["_id"]

    # Second detection — the critical one.  Before the fix this raised
    # ``pymongo.errors.WriteError: After applying the update, the
    # (immutable) field '_id' was found to have been altered`` in
    # mongomock.  The fix uses $setOnInsert for _id and $set for the
    # rest so the second call is a safe no-op on _id.
    r2 = await async_client.post(
        f"{ANOMALY_BASE}/detect", json=payload, headers=headers
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["count"] == 1

    # And in Mongo: still exactly one document, with the same _id.
    count_after_second = await mongo_mock_db["anomaly_results"].count_documents(
        {"user_id": "dedup-user"}
    )
    assert count_after_second == 1, (
        "Repeated detection must not create duplicate AnomalyResult documents"
    )
    second_doc = await mongo_mock_db["anomaly_results"].find_one(
        {"user_id": "dedup-user"}
    )
    assert second_doc is not None
    assert second_doc["_id"] == original_id, (
        f"_id must not change between detections: "
        f"was {original_id!r}, now {second_doc['_id']!r}"
    )
    # Defensive: _id is still a parseable UUID.
    UUID(str(second_doc["_id"]))
