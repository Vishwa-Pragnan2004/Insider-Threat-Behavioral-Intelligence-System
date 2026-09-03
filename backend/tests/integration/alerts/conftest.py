"""
ITBIS — Phase 6 Integration test fixtures.

Stand up a minimal FastAPI test stack:
  - in-memory SQLite for identity + RBAC
  - mongomock-motor for alerts/investigations/notes/anomaly_results
  - fakeredis for token store
  - identity seeder (creates ADMIN + 3 default roles)
  - helpers to register/login + promote a user to ADMIN
"""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.core.redis_client import get_redis
from app.main import app as fastapi_app
from app.modules.activity.infrastructure.models import (  # noqa: E402, F401
    IngestionErrorModel,
    IngestionJobModel,
)
from app.modules.behavioral.infrastructure.models import (  # noqa: E402, F401
    BehavioralBaselineModel,
)
from app.modules.identity.domain.enums import RoleName

# Force-import models so Base.metadata is populated
from app.modules.identity.infrastructure.models import (  # noqa: E402, F401
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

# Point at the Phase-5 model artifact so the anomaly pipeline (if
# exercised) doesn't try to load a real one.
PROJECT_ROOT = Path(__file__).resolve().parents[4]
os.environ.setdefault(
    "ITBIS_MODEL_PATH",
    str(PROJECT_ROOT / "ml_model" / "itbis_behavior_model_v2.joblib"),
)

# ─── Stack ────────────────────────────────────────────────


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

    # The alert observer is a process-wide singleton in the anomaly
    # module; reset it so each test gets a fresh one bound to this
    # test's mongo_mock_db.
    import app.modules.anomaly.presentation.dependencies as _dep
    _dep._observer_singleton = None

    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        yield client

    fastapi_app.dependency_overrides.clear()


# ─── Auth helpers ──────────────────────────────────────────


VALID_ADMIN = {
    "username": "alerts_admin",
    "email": "alerts.admin@example.com",
    "password": "SecurePass1!",
    "full_name": "Alerts Admin",
}
VALID_VIEWER = {
    "username": "alerts_viewer",
    "email": "alerts.viewer@example.com",
    "password": "SecurePass1!",
    "full_name": "Alerts Viewer",
}
VALID_INVESTIGATOR = {
    "username": "alerts_investigator",
    "email": "alerts.investigator@example.com",
    "password": "SecurePass1!",
    "full_name": "Alerts Investigator",
}
VALID_ANALYST = {
    "username": "alerts_analyst",
    "email": "alerts.analyst@example.com",
    "password": "SecurePass1!",
    "full_name": "Alerts Analyst",
}
AUTH_BASE = "/api/v1/auth"
ALERTS_BASE = "/api/v1/alerts"
INVESTIGATIONS_BASE = "/api/v1/investigations"
ANOMALY_BASE = "/api/v1/anomaly"


async def _register_and_promote(client, db, user, role: RoleName) -> str:
    r = await client.post(f"{AUTH_BASE}/register", json=user)
    assert r.status_code == 201, r.text
    user_repo = SQLUserRepository(db)
    role_repo = SQLRoleRepository(db)
    u = await user_repo.get_by_email(user["email"])
    r_ = await role_repo.get_by_name(role)
    u.assign_role(r_)
    # Only ADMIN gets superadmin (which would otherwise bypass RBAC).
    if role == RoleName.ADMIN:
        u._is_superadmin = True
    await user_repo.save(u)
    await db.commit()
    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def admin_token(client, db) -> str:
    return await _register_and_promote(client, db, VALID_ADMIN, RoleName.ADMIN)


async def viewer_token(client, db) -> str:
    return await _register_and_promote(client, db, VALID_VIEWER, RoleName.VIEWER)


async def investigator_token(client, db) -> str:
    return await _register_and_promote(
        client, db, VALID_INVESTIGATOR, RoleName.INVESTIGATOR
    )


async def analyst_token(client, db) -> str:
    return await _register_and_promote(
        client, db, VALID_ANALYST, RoleName.SECURITY_ANALYST
    )


# ─── Anomaly-result seed helper ──────────────────────────


def anomaly_doc(
    *,
    user_id: str = "u1",
    risk_level: str = "CRITICAL",
    risk_score: float = 90.0,
    prediction: str = "anomaly",
    source_dataset: str = "cert",
    window: str = "daily",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    model_version: str = "itbis_behavior_v2",
    feature_version: str = "behavioral_features_v1",
) -> dict:
    if window_start is None:
        window_start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    if window_end is None:
        window_end = datetime(2026, 8, 2, 0, 0, tzinfo=UTC)
    return {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "source_dataset": source_dataset,
        "window": window,
        "window_start": window_start,
        "window_end": window_end,
        "model_version": model_version,
        "feature_version": feature_version,
        "prediction": prediction,
        "raw_anomaly_score": -0.05,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "baseline_source": "personal",
        "top_behavioral_deviations": [
            {
                "feature": "usb_activity_count",
                "value": 10.0,
                "baseline_mean": 0.5,
                "baseline_std": 1.0,
                "zscore": 9.5,
            }
        ],
        "model_input": {},
        "created_at": datetime.now(UTC),
    }
