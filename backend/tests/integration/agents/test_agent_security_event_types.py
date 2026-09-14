"""
ITBIS — Integration tests: event types emitted by the endpoint agent's
account, privilege and remote-access collection.

The backend's CanonicalEvent validates `event_type` against its enum, so a
type the backend doesn't know rejects the *entire* batch with 422 — and the
agent treats 422 as permanent and dead-letters it. The backend enum must
therefore learn a new type before any agent sends it; these tests pin that.
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
EVENTS_URL = "/api/v1/ingestion/events"

ADMIN = {
    "username": "sec_types_admin",
    "email": "sec.types.admin@example.com",
    "password": "SecurePass1!",
    "full_name": "Security Types Admin",
}


async def _enrolled_device_key(client: AsyncClient, db: AsyncSession, device_id: str) -> str:
    r = await client.post(f"{AUTH_BASE}/register", json=ADMIN)
    assert r.status_code == 201, r.text
    users, roles = SQLUserRepository(db), SQLRoleRepository(db)
    user = await users.get_by_email(ADMIN["email"])
    user.assign_role(await roles.get_by_name(RoleName.ADMIN))
    user._is_superadmin = True
    await users.save(user)
    await db.commit()

    r = await client.post(
        f"{AUTH_BASE}/login",
        json={"email": ADMIN["email"], "password": ADMIN["password"]},
    )
    token = r.json()["access_token"]
    r = await client.post(
        "/api/v1/agents/enroll",
        json={"device_id": device_id, "device_name": device_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


def _event(event_type: str, **extra) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "raw_event_id": f"{event_type}-{uuid.uuid4().hex}",
        "timestamp": datetime.now(UTC).isoformat(),
        "event_type": event_type,
        "user_id": "CORP\\jsmith",
        "source_dataset": "win_endpoint",
        **extra,
    }


AGENT_SECURITY_TYPES = [
    "remote_session_connect",
    "remote_session_disconnect",
    "privilege_change",
    "group_change",
    "account_created",
    "account_disabled",
    "password_change",
]


@pytest.mark.asyncio
async def test_backend_accepts_every_agent_security_event_type(
    async_client: AsyncClient, db_session: AsyncSession
):
    key = await _enrolled_device_key(async_client, db_session, "WS-SEC")
    events = [
        _event(
            t,
            is_remote=t.startswith("remote_session"),
            risk_indicators=["privileged_group_member_added"] if t == "privilege_change" else [],
            enrichments={"change": "member_added"},
            tags=["win_endpoint", "remote_access"],
        )
        for t in AGENT_SECURITY_TYPES
    ]

    r = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-SEC", "events": events},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == len(AGENT_SECURITY_TYPES)
    assert body["rejected"] == 0


@pytest.mark.asyncio
async def test_unknown_event_type_rejects_the_whole_batch(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Why the backend enum must be updated before the agent ships a new type."""
    key = await _enrolled_device_key(async_client, db_session, "WS-SEC2")
    r = await async_client.post(
        EVENTS_URL,
        json={
            "agent_id": "WS-SEC2",
            "events": [_event("logon"), _event("definitely_not_a_type")],
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 422
