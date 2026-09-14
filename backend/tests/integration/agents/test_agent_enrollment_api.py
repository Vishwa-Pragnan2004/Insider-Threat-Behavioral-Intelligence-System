"""
ITBIS — Integration tests: agent device enrollment.

Covers:
  - POST   /api/v1/agents/enroll
  - GET    /api/v1/agents
  - POST   /api/v1/agents/{device_id}/rotate
  - DELETE /api/v1/agents/{device_id}
  - the enrolled credential working (and being revocable) against
    POST /api/v1/ingestion/events

Uses the shared stack in tests/integration/conftest.py.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)

AUTH_BASE = "/api/v1/auth"
AGENTS_BASE = "/api/v1/agents"
EVENTS_URL = "/api/v1/ingestion/events"

ADMIN = {
    "username": "agents_admin",
    "email": "agents.admin@example.com",
    "password": "SecurePass1!",
    "full_name": "Agents Admin",
}
VIEWER = {
    "username": "agents_viewer",
    "email": "agents.viewer@example.com",
    "password": "SecurePass1!",
    "full_name": "Agents Viewer",
}


async def _register_with_role(
    client: AsyncClient, db: AsyncSession, user: dict, role: RoleName
) -> str:
    r = await client.post(f"{AUTH_BASE}/register", json=user)
    assert r.status_code == 201, r.text
    user_repo = SQLUserRepository(db)
    role_repo = SQLRoleRepository(db)
    u = await user_repo.get_by_email(user["email"])
    role_obj = await role_repo.get_by_name(role)
    u.assign_role(role_obj)
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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _event(user_id: str = "CORP\\jsmith") -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "raw_event_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": "logon",
        "user_id": user_id,
        "source_dataset": "win_endpoint",
    }


# ─── Enrollment ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enroll_requires_auth(async_client: AsyncClient):
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll", json={"device_id": "WS-1", "device_name": "Laptop"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_enroll_requires_agents_manage(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, VIEWER, RoleName.VIEWER)
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll",
        json={"device_id": "WS-1", "device_name": "Laptop"},
        headers=_headers(token),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_enroll_returns_key_once(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll",
        json={"device_id": "WS-1", "device_name": "Laptop 1"},
        headers=_headers(token),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["api_key"].startswith("itbis_ag_")
    assert body["device"]["device_id"] == "WS-1"
    assert body["device"]["is_active"] is True

    # The secret must never come back from a listing.
    r = await async_client.get(AGENTS_BASE, headers=_headers(token))
    assert r.status_code == 200
    listed = r.json()
    assert len(listed) == 1
    assert "api_key" not in listed[0]
    assert "key_hash" not in listed[0]


@pytest.mark.asyncio
async def test_duplicate_enrollment_conflicts(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    payload = {"device_id": "WS-1", "device_name": "Laptop 1"}
    r1 = await async_client.post(
        f"{AGENTS_BASE}/enroll", json=payload, headers=_headers(token)
    )
    assert r1.status_code == 201
    r2 = await async_client.post(
        f"{AGENTS_BASE}/enroll", json=payload, headers=_headers(token)
    )
    assert r2.status_code == 409


# ─── The credential actually works for ingest ───────────────


@pytest.mark.asyncio
async def test_enrolled_device_can_ingest_events(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll",
        json={"device_id": "WS-1", "device_name": "Laptop 1"},
        headers=_headers(token),
    )
    api_key = r.json()["api_key"]

    r = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-1", "events": [_event()]},
        headers=_headers(api_key),
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_device_cannot_submit_as_another_device(
    async_client: AsyncClient, db_session: AsyncSession
):
    """A stolen key must not let a host impersonate a different machine."""
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll",
        json={"device_id": "WS-1", "device_name": "Laptop 1"},
        headers=_headers(token),
    )
    api_key = r.json()["api_key"]

    r = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-2", "events": [_event()]},
        headers=_headers(api_key),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bogus_device_key_is_rejected(async_client: AsyncClient):
    r = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-1", "events": [_event()]},
        headers=_headers("itbis_ag_deadbeefcafe_notarealsecret"),
    )
    assert r.status_code == 401


# ─── Revocation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoked_device_is_locked_out(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll",
        json={"device_id": "WS-1", "device_name": "Laptop 1"},
        headers=_headers(token),
    )
    api_key = r.json()["api_key"]

    ok = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-1", "events": [_event()]},
        headers=_headers(api_key),
    )
    assert ok.status_code == 200

    r = await async_client.delete(f"{AGENTS_BASE}/WS-1", headers=_headers(token))
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    denied = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-1", "events": [_event()]},
        headers=_headers(api_key),
    )
    assert denied.status_code == 401


@pytest.mark.asyncio
async def test_revoking_one_device_does_not_affect_another(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    keys = {}
    for dev in ("WS-A", "WS-B"):
        r = await async_client.post(
            f"{AGENTS_BASE}/enroll",
            json={"device_id": dev, "device_name": dev},
            headers=_headers(token),
        )
        keys[dev] = r.json()["api_key"]

    await async_client.delete(f"{AGENTS_BASE}/WS-A", headers=_headers(token))

    a = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-A", "events": [_event()]},
        headers=_headers(keys["WS-A"]),
    )
    b = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-B", "events": [_event()]},
        headers=_headers(keys["WS-B"]),
    )
    assert a.status_code == 401
    assert b.status_code == 200


@pytest.mark.asyncio
async def test_rotate_invalidates_old_key(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(
        f"{AGENTS_BASE}/enroll",
        json={"device_id": "WS-1", "device_name": "Laptop 1"},
        headers=_headers(token),
    )
    old_key = r.json()["api_key"]

    r = await async_client.post(f"{AGENTS_BASE}/WS-1/rotate", headers=_headers(token))
    assert r.status_code == 200
    new_key = r.json()["api_key"]
    assert new_key != old_key

    old = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-1", "events": [_event()]},
        headers=_headers(old_key),
    )
    new = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-1", "events": [_event()]},
        headers=_headers(new_key),
    )
    assert old.status_code == 401
    assert new.status_code == 200


@pytest.mark.asyncio
async def test_rotate_and_revoke_unknown_device_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(f"{AGENTS_BASE}/nope/rotate", headers=_headers(token))
    assert r.status_code == 404
    r = await async_client.delete(f"{AGENTS_BASE}/nope", headers=_headers(token))
    assert r.status_code == 404


# ─── The user path still works ──────────────────────────────


@pytest.mark.asyncio
async def test_user_with_agent_ingest_can_still_post(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Scripted ingestion (demo pipeline, back-fills) must keep working."""
    token = await _register_with_role(async_client, db_session, ADMIN, RoleName.ADMIN)
    r = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "manual-backfill", "events": [_event()]},
        headers=_headers(token),
    )
    assert r.status_code == 200, r.text
    assert r.json()["accepted"] == 1
