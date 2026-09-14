"""
ITBIS — Integration tests: continuous detection pipeline API.

Seeds raw canonical events (what the endpoint agent and CSV ingestion store)
and checks that one pipeline run turns them into behavioural features, a
personal baseline, anomaly results and an alert — a path that previously
needed several manual API calls.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from app.modules.ueba.application import detection_pipeline

AUTH = "/api/v1/auth"
PIPELINE = "/api/v1/ueba/pipeline"
INSIDER = "insider.jane"

#: A day of activity far outside any normal baseline.
BURST_EVENT_TYPES = [
    "logon",
    "logon_failed",
    "file_copy",
    "file_write",
    "usb_insert",
    "email_sent",
    "email_external",
    "http_request",
    "privilege_change",
    "app_launch",
]


@pytest_asyncio.fixture(autouse=True)
async def _fresh_pipeline_status():
    detection_pipeline.pipeline_coordinator.status = detection_pipeline.PipelineStatus()
    yield


async def _token(client: AsyncClient, db: AsyncSession, role: RoleName) -> str:
    name = f"pipeline_{role.value.lower()}"
    user = {
        "username": name,
        "email": f"{name}@example.com",
        "password": "SecurePass1!",
        "full_name": name,
    }
    r = await client.post(f"{AUTH}/register", json=user)
    assert r.status_code == 201, r.text
    users, roles = SQLUserRepository(db), SQLRoleRepository(db)
    entity = await users.get_by_email(user["email"])
    entity.assign_role(await roles.get_by_name(role))
    if role == RoleName.ADMIN:
        entity._is_superadmin = True
    await users.save(entity)
    await db.commit()
    r = await client.post(
        f"{AUTH}/login", json={"email": user["email"], "password": user["password"]}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _burst_of_activity(user_id: str, repeats: int = 60) -> list[dict]:
    now = datetime.now(UTC)
    docs = []
    for i in range(repeats):
        for k, event_type in enumerate(BURST_EVENT_TYPES):
            ts = now - timedelta(seconds=i * 5 + k)
            docs.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "raw_event_id": f"burst-{i}-{k}",
                    "event_type": event_type,
                    "timestamp": ts.isoformat().replace("+00:00", "Z"),
                    "user_id": user_id,
                    "source_dataset": "win_endpoint",
                    "device_id": f"WS-{i % 5}",
                    "target_resource": f"/share/doc-{i}-{k}.xlsx",
                }
            )
    return docs


def _quiet_history(user_id: str, days: int = 7) -> list[dict]:
    """A few logons a day, on the days before the pipeline's scoring window."""
    today = datetime.now(UTC).replace(hour=10, minute=0, second=0, microsecond=0)
    docs = []
    for day in range(2, 2 + days):  # the window covers today and yesterday
        for n in range(3):
            ts = today - timedelta(days=day) + timedelta(minutes=n * 20)
            docs.append(
                {
                    "event_id": str(uuid.uuid4()),
                    "raw_event_id": f"quiet-{day}-{n}",
                    "event_type": "logon",
                    "timestamp": ts.isoformat().replace("+00:00", "Z"),
                    "user_id": user_id,
                    "source_dataset": "win_endpoint",
                    "device_id": "WS-0",
                }
            )
    return docs


# ─── Access control ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_endpoints_require_auth(async_client: AsyncClient):
    assert (await async_client.get(f"{PIPELINE}/status")).status_code == 401
    assert (await async_client.post(f"{PIPELINE}/run")).status_code == 401


@pytest.mark.asyncio
async def test_viewer_can_see_status_but_not_trigger_a_run(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _token(async_client, db_session, RoleName.VIEWER)
    assert (await async_client.get(f"{PIPELINE}/status", headers=_headers(token))).status_code == 200
    assert (await async_client.post(f"{PIPELINE}/run", headers=_headers(token))).status_code == 403


# ─── End to end ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_run_turns_raw_activity_into_an_alert(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token = await _token(async_client, db_session, RoleName.ADMIN)
    await mongo_mock_db["canonical_events"].insert_many(
        _quiet_history(INSIDER) + _burst_of_activity(INSIDER)
    )

    r = await async_client.post(f"{PIPELINE}/run", headers=_headers(token))

    assert r.status_code == 200, r.text
    run = r.json()
    assert run["succeeded"], run["error"]
    assert run["trigger"] == "manual"
    assert run["feature_rows"] >= 1
    assert run["users_with_features"] == 1
    assert run["baselines_built"] == 1, run
    assert run["findings"] >= 1 and run["risk_scores"] >= 1, run
    assert run["anomaly_results"] >= 1
    assert run["high_risk_results"] >= 1, run
    assert run["alerts_created"] >= 1, run

    results = await async_client.get(
        f"/api/v1/anomaly/users/{INSIDER}/results", headers=_headers(token)
    )
    assert results.status_code == 200, results.text
    assert results.json()["results"], "detection results are queryable afterwards"


@pytest.mark.asyncio
async def test_rerunning_the_same_window_does_not_duplicate_alerts(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token = await _token(async_client, db_session, RoleName.ADMIN)
    await mongo_mock_db["canonical_events"].insert_many(
        _quiet_history(INSIDER) + _burst_of_activity(INSIDER)
    )

    first = (await async_client.post(f"{PIPELINE}/run", headers=_headers(token))).json()
    second = (await async_client.post(f"{PIPELINE}/run", headers=_headers(token))).json()

    assert first["alerts_created"] >= 1
    assert second["succeeded"], second["error"]
    assert second["anomaly_results"] == first["anomaly_results"]
    assert second["alerts_created"] == 0
    assert second["baselines_built"] == 0, "the baseline is already up to date"


@pytest.mark.asyncio
async def test_user_without_history_is_scored_but_not_alerted(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    """
    A heavy but not intrinsically suspicious day from someone with no history:
    the model scores it, detectors that need a personal history wait, and no
    alert is raised. (Red flags that don't depend on history, like a burst of
    failed logons, would still alert.)
    """
    token = await _token(async_client, db_session, RoleName.ADMIN)
    burst = [e for e in _burst_of_activity(INSIDER) if e["event_type"] != "logon_failed"]
    await mongo_mock_db["canonical_events"].insert_many(burst)

    run = (await async_client.post(f"{PIPELINE}/run", headers=_headers(token))).json()

    assert run["succeeded"], run["error"]
    assert run["baselines_built"] == 0
    assert run["anomaly_results"] >= 1
    assert run["alerts_created"] == 0, "still in the learning period"


@pytest.mark.asyncio
async def test_run_with_no_activity_skips_detection(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _token(async_client, db_session, RoleName.ADMIN)

    run = (await async_client.post(f"{PIPELINE}/run", headers=_headers(token))).json()

    assert run["succeeded"]
    assert run["feature_rows"] == 0
    assert run["detection_skipped_reason"] == detection_pipeline.NO_ACTIVITY
    assert run["alerts_created"] == 0


@pytest.mark.asyncio
async def test_status_reports_the_last_run(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token = await _token(async_client, db_session, RoleName.ADMIN)
    await mongo_mock_db["canonical_events"].insert_many(_burst_of_activity(INSIDER, repeats=5))
    run = (await async_client.post(f"{PIPELINE}/run", headers=_headers(token))).json()

    status = (await async_client.get(f"{PIPELINE}/status", headers=_headers(token))).json()

    assert status["runs_completed"] == 1
    assert status["runs_failed"] == 0
    assert status["running"] is False
    assert status["last_run"]["run_id"] == run["run_id"]
    assert status["last_success_at"] is not None
