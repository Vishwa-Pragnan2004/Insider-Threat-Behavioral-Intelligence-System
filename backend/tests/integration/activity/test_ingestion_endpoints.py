"""
ITBIS — Integration tests for the Activity ingestion API.

Covers:
  - Upload a valid logon CSV
  - Job status reflects processing outcome
  - Stats endpoint aggregates
  - Malformed records produce a PARTIAL job and recorded errors
  - Empty file returns 400
  - Unsupported log type returns 400
  - All endpoints require auth (401)
  - Endpoints enforce RBAC (403 for insufficient permission)
  - Events are persisted to MongoDB
  - Schema variation (column aliases) is accepted
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from tests.integration.activity.conftest import (
    AUTH_BASE,
    INGESTION_BASE,
    register_and_login,
)

VALID_LOGON_CSV = (
    b"id,date,user,pc,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"
    b"2,01/02/2010 17:00:00,alice,PC1,Logoff\n"
    b"3,01/03/2010 08:00:00,bob,PC2,Logon\n"
)

MALFORMED_LOGON_CSV = (
    b"id,date,user,pc,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"
    b"2,NOTADATE,alice,PC1,Logoff\n"
    b"3,01/02/2010 08:05:00,,PC2,Logon\n"
    b"4,01/02/2010 17:05:00,bob,PC2,Logoff\n"
)

ALIAS_LOGON_CSV = (
    b"id,timestamp,userid,hostname,activity\n"
    b"1,01/02/2010 08:00:00,alice,PC1,Logon\n"
    b"2,01/02/2010 17:00:00,alice,PC1,Logoff\n"
)


# ─── helpers ────────────────────────────────────────────────


async def _login_as_admin(client: AsyncClient, db_session: AsyncSession) -> str:
    """Register, promote to ADMIN in DB, re-login, return access token."""
    await register_and_login(client)

    user_repo = SQLUserRepository(db_session)
    role_repo = SQLRoleRepository(db_session)
    user = await user_repo.get_by_email("activity.tester@example.com")
    admin_role = await role_repo.get_by_name(RoleName.ADMIN)
    assert admin_role is not None
    user._is_superadmin = True
    user.assign_role(admin_role)
    await user_repo.save(user)
    await db_session.commit()

    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": "activity.tester@example.com", "password": "SecurePass1!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ─── Auth / RBAC guards ──────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_requires_auth(async_client: AsyncClient):
    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", VALID_LOGON_CSV, "text/csv")},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_list_jobs_requires_auth(async_client: AsyncClient):
    r = await async_client.get(f"{INGESTION_BASE}/jobs")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_stats_requires_auth(async_client: AsyncClient):
    r = await async_client.get(f"{INGESTION_BASE}/stats")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_endpoints_reject_viewer_role(async_client: AsyncClient):
    """A default VIEWER user lacks alerts:create (so uploads must 403).

    VIEWER does have alerts:read so /stats returns 200 — covered by
    test_stats_endpoint_aggregates which uses an admin token.
    """
    token = await register_and_login(async_client)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", VALID_LOGON_CSV, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 403


# ─── Happy path: upload → status → stats ─────────────────────


@pytest.mark.asyncio
async def test_upload_valid_logon_csv(async_client: AsyncClient, test_db_session: AsyncSession):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", VALID_LOGON_CSV, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job"]["log_type"] == "logon"
    assert body["job"]["total_rows"] == 3
    assert body["job"]["events_stored"] == 3
    assert body["job"]["status"] in ("completed", "partial")
    assert "completed" in body["message"].lower()


@pytest.mark.asyncio
async def test_get_job_status_returns_full_state(
    async_client: AsyncClient, test_db_session: AsyncSession
):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", VALID_LOGON_CSV, "text/csv")},
        headers=headers,
    )
    job_id = r.json()["job"]["id"]

    r2 = await async_client.get(f"{INGESTION_BASE}/jobs/{job_id}", headers=headers)
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == job_id
    assert body["log_type"] == "logon"


@pytest.mark.asyncio
async def test_get_nonexistent_job_returns_404(
    async_client: AsyncClient, test_db_session: AsyncSession
):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.get(
        f"{INGESTION_BASE}/jobs/00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_returns_recent(async_client: AsyncClient, test_db_session: AsyncSession):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(2):
        await async_client.post(
            f"{INGESTION_BASE}/upload",
            files={"file": (f"logon_{i}.csv", VALID_LOGON_CSV, "text/csv")},
            headers=headers,
        )

    r = await async_client.get(f"{INGESTION_BASE}/jobs", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert len(body["jobs"]) == 2


@pytest.mark.asyncio
async def test_stats_endpoint_aggregates(async_client: AsyncClient, test_db_session: AsyncSession):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", VALID_LOGON_CSV, "text/csv")},
        headers=headers,
    )

    r = await async_client.get(f"{INGESTION_BASE}/stats", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total_jobs"] == 1
    assert body["total_events_stored"] == 3
    assert body["jobs_by_log_type"].get("logon") == 1


# ─── Malformed records → PARTIAL + errors endpoint ──────────


@pytest.mark.asyncio
async def test_upload_with_malformed_rows(async_client: AsyncClient, test_db_session: AsyncSession):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", MALFORMED_LOGON_CSV, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job"]["status"] == "partial"
    assert body["job"]["failed_rows"] == 2
    assert body["job"]["events_stored"] == 2

    job_id = body["job"]["id"]
    r2 = await async_client.get(f"{INGESTION_BASE}/jobs/{job_id}/errors", headers=headers)
    assert r2.status_code == 200
    errors_body = r2.json()
    assert errors_body["count"] == 2
    assert errors_body["job_id"] == job_id


# ─── Validation errors ──────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_empty_file_returns_400(
    async_client: AsyncClient, test_db_session: AsyncSession
):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_unknown_columns_returns_400(
    async_client: AsyncClient, test_db_session: AsyncSession
):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("bogus.csv", b"foo,bar\n1,2\n", "text/csv")},
        headers=headers,
    )
    assert r.status_code == 400


# ─── Schema variation ──────────────────────────────────────


@pytest.mark.asyncio
async def test_upload_with_column_aliases(async_client: AsyncClient, test_db_session: AsyncSession):
    """CSV with renamed columns (userid/timestamp) should still ingest."""
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", ALIAS_LOGON_CSV, "text/csv")},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job"]["log_type"] == "logon"
    assert body["job"]["events_stored"] == 2


# ─── Mongo persistence ──────────────────────────────────────


@pytest.mark.asyncio
async def test_events_persisted_to_mongo(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
    mongo_mock_db,
):
    token = await _login_as_admin(async_client, test_db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INGESTION_BASE}/upload",
        files={"file": ("logon.csv", VALID_LOGON_CSV, "text/csv")},
        headers=headers,
    )
    job_id = r.json()["job"]["id"]

    count = await mongo_mock_db["canonical_events"].count_documents({"job_id": job_id})
    assert count == 3

    doc = await mongo_mock_db["canonical_events"].find_one({"job_id": job_id})
    assert doc is not None
    assert "event_type" in doc
    assert "user_id" in doc
    assert "timestamp" in doc
