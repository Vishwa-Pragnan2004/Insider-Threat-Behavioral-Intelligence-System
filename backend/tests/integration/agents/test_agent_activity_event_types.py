"""
ITBIS — Integration tests: file, download, data-transfer and network events
from the endpoint agent.

These carry `bytes_transferred` / `file_count`, and must be accepted by the
backend's CanonicalEvent before the agent ships them (an unknown type rejects
the whole batch — see test_agent_security_event_types.py).
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
    "username": "activity_types_admin",
    "email": "activity.types.admin@example.com",
    "password": "SecurePass1!",
    "full_name": "Activity Types Admin",
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
        "user_id": "vishw",
        "source_dataset": "win_endpoint",
        **extra,
    }


@pytest.mark.asyncio
async def test_backend_accepts_agent_file_download_transfer_and_network_events(
    async_client: AsyncClient, db_session: AsyncSession
):
    key = await _enrolled_device_key(async_client, db_session, "WS-ACT")
    events = [
        _event("file_copy", target_type="removable_media", bytes_transferred=4096, file_count=1,
               risk_indicators=["file_copied_to_removable_media"]),
        _event("file_write", target_type="removable_media", bytes_transferred=100, file_count=1),
        _event("file_delete", target_type="removable_media", file_count=1),
        _event("file_move", target_type="removable_media", file_count=1),
        _event("data_transfer", target_type="removable_media", bytes_transferred=10_240,
               file_count=3),
        _event("file_download", target_type="file", bytes_transferred=2048, file_count=1,
               enrichments={"source_host": "files.example.com", "zone_name": "Internet"}),
        _event("network_connection", target_type="network_endpoint",
               target_resource="93.184.216.34:443",
               enrichments={"direction": "outbound", "remote_scope": "public"}),
    ]

    r = await async_client.post(
        EVENTS_URL,
        json={"agent_id": "WS-ACT", "events": events},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == len(events)
    assert body["rejected"] == 0
