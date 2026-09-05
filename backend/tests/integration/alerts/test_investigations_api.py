"""
ITBIS — Integration tests: investigations API.

Covers:
  - 401 on every endpoint when unauthenticated
  - RBAC for INVESTIGATOR (read+create+update) and VIEWER (read-only)
  - full lifecycle
  - link/unlink alerts
  - notes are immutable
  - illegal status transition -> 409
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.alerts.conftest import (
    ALERTS_BASE,
    INVESTIGATIONS_BASE,
    analyst_token,
    anomaly_doc,
    investigator_token,
    viewer_token,
)

# ─── 401 / RBAC ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(async_client: AsyncClient):
    r = await async_client.get(f"{INVESTIGATIONS_BASE}/")
    assert r.status_code == 401
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/", json={"title": "valid title"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_viewer_can_only_read(async_client: AsyncClient, db_session: AsyncSession):
    token = await viewer_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.get(f"{INVESTIGATIONS_BASE}/", headers=headers)
    assert r.status_code == 200
    # Viewer lacks investigations:create — must 403 (NOT 422, the body
    # is valid: title has > 3 chars).
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title"},
        headers=headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_investigator_can_create_and_update(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "investigation", "severity": "HIGH"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/status",
        json={"status": "IN_PROGRESS"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "IN_PROGRESS"


# ─── Create / get / list ────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_investigation(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "title": "Phishing campaign",
        "description": "Multiple users received suspicious links",
        "severity": "HIGH",
        "related_user_ids": ["alice", "bob"],
        "related_alert_ids": [str(uuid.uuid4())],
        "assigned_to": "alice",
    }
    r = await async_client.post(f"{INVESTIGATIONS_BASE}/", json=body, headers=headers)
    assert r.status_code == 201
    iid = r.json()["id"]

    r = await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["title"] == "Phishing campaign"
    assert r.json()["related_user_ids"] == ["alice", "bob"]


@pytest.mark.asyncio
async def test_get_investigation_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    r = await async_client.get(
        f"{INVESTIGATIONS_BASE}/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_pagination(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    for i in range(3):
        await async_client.post(
            f"{INVESTIGATIONS_BASE}/",
            json={"title": f"inv-{i}", "severity": "LOW"},
            headers=headers,
        )
    r = await async_client.get(
        f"{INVESTIGATIONS_BASE}/", params={"limit": 2, "skip": 0}, headers=headers
    )
    body = r.json()
    assert body["total"] == 3
    assert body["count"] == 2


# ─── Lifecycle ────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifecycle_open_to_closed(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]

    for target in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        r = await async_client.post(
            f"{INVESTIGATIONS_BASE}/{iid}/status",
            json={"status": target},
            headers=headers,
        )
        assert r.status_code == 200, (target, r.text)
        assert r.json()["status"] == target
    # closed_at is set
    assert r.json()["closed_at"] is not None


@pytest.mark.asyncio
async def test_illegal_status_transition_returns_409(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]
    # OPEN -> CLOSED is illegal
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/status",
        json={"status": "CLOSED"},
        headers=headers,
    )
    assert r.status_code == 409


# ─── Link / unlink alerts ────────────────────────────


@pytest.mark.asyncio
async def test_link_and_unlink_alert(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token = await analyst_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed an anomaly so we can generate an alert to link
    await mongo_mock_db["anomaly_results"].insert_one(
        anomaly_doc(user_id="alice", risk_level="CRITICAL")
    )
    await async_client.post(f"{ALERTS_BASE}/generate", json={"limit": 100}, headers=headers)
    aid = (await async_client.get(f"{ALERTS_BASE}/", headers=headers)).json()["alerts"][0]["id"]

    # Create an investigation and link the alert
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]

    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/alerts",
        json={"alert_id": aid, "user_id": "alice"},
        headers=headers,
    )
    assert r.status_code == 200
    assert aid in r.json()["related_alert_ids"]
    assert "alice" in r.json()["related_user_ids"]

    # Verify the alert is also linked to the investigation on the alert side
    r = await async_client.get(f"{ALERTS_BASE}/{aid}", headers=headers)
    assert r.json()["investigation_id"] == iid

    # Unlink
    r = await async_client.delete(
        f"{INVESTIGATIONS_BASE}/{iid}/alerts/{aid}",
        headers=headers,
    )
    assert r.status_code == 200
    assert aid not in r.json()["related_alert_ids"]


# ─── Notes ──────────────────────────────────────


@pytest.mark.asyncio
async def test_notes_are_appended_in_order(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]

    for body in ("first", "second", "third"):
        r = await async_client.post(
            f"{INVESTIGATIONS_BASE}/{iid}/notes",
            json={"content": body},
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["content"] == body

    r = await async_client.get(
        f"{INVESTIGATIONS_BASE}/{iid}/notes",
        headers=headers,
    )
    body = r.json()
    assert body["count"] == 3
    contents = [n["content"] for n in body["notes"]]
    assert contents == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_investigation_detail_includes_notes(
    async_client: AsyncClient, db_session: AsyncSession
):
    """GET /investigations/{id} should include all notes in the response."""
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "Investigation with notes", "severity": "HIGH"},
        headers=headers,
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    for content in ("Initial assessment", "Evidence collected", "Escalated to SOC"):
        r = await async_client.post(
            f"{INVESTIGATIONS_BASE}/{iid}/notes",
            json={"content": content},
            headers=headers,
        )
        assert r.status_code == 201

    r = await async_client.get(
        f"{INVESTIGATIONS_BASE}/{iid}",
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Investigation with notes"
    assert body["notes"] is not None
    assert len(body["notes"]) == 3
    contents = [n["content"] for n in body["notes"]]
    assert contents == ["Initial assessment", "Evidence collected", "Escalated to SOC"]


@pytest.mark.asyncio
async def test_notes_have_no_update_or_delete_endpoints(
    async_client: AsyncClient, db_session: AsyncSession
):
    """
    Notes are immutable — there should be no API endpoint to update or
    delete them.  This test verifies the router does not expose such
    methods (they would 405 or 404 if called).
    """
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/notes",
        json={"content": "x"},
        headers=headers,
    )
    assert r.status_code == 201
    nid = r.json()["id"]

    # Try PATCH/PUT/DELETE on the note — should not be a valid route
    r = await async_client.put(
        f"{INVESTIGATIONS_BASE}/{iid}/notes/{nid}",
        json={"content": "modified"},
        headers=headers,
    )
    assert r.status_code in (404, 405)
    r = await async_client.patch(
        f"{INVESTIGATIONS_BASE}/{iid}/notes/{nid}",
        json={"content": "modified"},
        headers=headers,
    )
    assert r.status_code in (404, 405)
    r = await async_client.delete(
        f"{INVESTIGATIONS_BASE}/{iid}/notes/{nid}",
        headers=headers,
    )
    assert r.status_code in (404, 405)

    # The note must still be present, unchanged
    r = await async_client.get(
        f"{INVESTIGATIONS_BASE}/{iid}/notes",
        headers=headers,
    )
    assert r.json()["count"] == 1
    assert r.json()["notes"][0]["content"] == "x"


@pytest.mark.asyncio
async def test_add_note_to_missing_investigation_returns_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    token = await investigator_token(async_client, db_session)
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/00000000-0000-0000-0000-000000000000/notes",
        json={"content": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


# ─── Investigation workflow end-to-end ─────────────


@pytest.mark.asyncio
async def test_full_investigation_workflow_with_alert(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    """End-to-end: generate alert -> create investigation -> link
    alert -> status lifecycle -> add notes -> close."""
    token = await analyst_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Generate an alert from an anomaly result
    await mongo_mock_db["anomaly_results"].insert_one(
        anomaly_doc(user_id="alice", risk_level="CRITICAL")
    )
    await async_client.post(f"{ALERTS_BASE}/generate", json={"limit": 100}, headers=headers)
    aid = (await async_client.get(f"{ALERTS_BASE}/", headers=headers)).json()["alerts"][0]["id"]

    # 2. Create an investigation linked to the alert
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={
            "title": "Compromised account",
            "description": "Suspected credential theft",
            "severity": "CRITICAL",
            "related_alert_ids": [aid],
            "related_user_ids": ["alice"],
            "assigned_to": "alice",
        },
        headers=headers,
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    # 3. Walk the lifecycle
    for s in ("IN_PROGRESS", "RESOLVED", "CLOSED"):
        r = await async_client.post(
            f"{INVESTIGATIONS_BASE}/{iid}/status",
            json={"status": s},
            headers=headers,
        )
        assert r.status_code == 200, (s, r.text)
        assert r.json()["status"] == s

    # 4. Add notes
    for content in ("Investigating logs", "Suspect was terminated", "Closed"):
        r = await async_client.post(
            f"{INVESTIGATIONS_BASE}/{iid}/notes",
            json={"content": content},
            headers=headers,
        )
        assert r.status_code == 201

    # 5. Verify final state
    r = await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}", headers=headers)
    inv = r.json()
    assert inv["status"] == "CLOSED"
    assert inv["closed_at"] is not None
    assert aid in inv["related_alert_ids"]
    assert "alice" in inv["related_user_ids"]
    r = await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}/notes", headers=headers)
    assert r.json()["count"] == 3


# ─── FIX 3: user-existence validation (investigations) ────────────


@pytest.mark.asyncio
async def test_assign_investigation_to_existing_user_succeeds(
    async_client: AsyncClient, db_session: AsyncSession
):
    from app.modules.identity.infrastructure.repositories import (
        SQLUserRepository,
    )

    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    user_repo = SQLUserRepository(db_session)
    inv = await user_repo.get_by_email("alerts.investigator@example.com")
    assert inv is not None
    real_user_id = str(inv.id)

    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    r2 = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/assign",
        json={"user_id": real_user_id},
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["assigned_to"] == real_user_id


@pytest.mark.asyncio
async def test_assign_investigation_to_nonexistent_user_returns_404(
    async_client: AsyncClient, db_session: AsyncSession
):
    """FIX 3: assigning to a non-existent user must 404 (not store the bad ref)."""
    token = await investigator_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    bogus = "00000000-0000-0000-0000-000000000000"
    r2 = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/assign",
        json={"user_id": bogus},
        headers=headers,
    )
    assert r2.status_code == 404

    # And the investigation was NOT assigned.
    r3 = await async_client.get(
        f"{INVESTIGATIONS_BASE}/{iid}", headers=headers
    )
    assert r3.json()["assigned_to"] is None


# ─── FIX 4: alert ↔ investigation link/unlink integration ─────


@pytest.mark.asyncio
async def test_link_alert_updates_both_sides(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    """
    FIX 4: POST /investigations/{id}/alerts must update BOTH:
      - the investigation's related_alert_ids
      - the alert's investigation_id
    """
    token = await analyst_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Seed an anomaly and generate an alert.
    await mongo_mock_db["anomaly_results"].insert_one(
        anomaly_doc(user_id="alice", risk_level="CRITICAL")
    )
    await async_client.post(
        f"{ALERTS_BASE}/generate", json={"limit": 100}, headers=headers
    )
    aid = (await async_client.get(f"{ALERTS_BASE}/", headers=headers)).json()["alerts"][0]["id"]

    # Create an investigation.
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    assert r.status_code == 201
    iid = r.json()["id"]

    # Link the alert.
    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/alerts",
        json={"alert_id": aid, "user_id": "alice"},
        headers=headers,
    )
    assert r.status_code == 200
    assert aid in r.json()["related_alert_ids"]

    # Both sides are consistent.
    alert = (await async_client.get(f"{ALERTS_BASE}/{aid}", headers=headers)).json()
    inv = (await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}", headers=headers)).json()
    assert alert["investigation_id"] == iid
    assert aid in inv["related_alert_ids"]


@pytest.mark.asyncio
async def test_link_alert_twice_is_idempotent(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    """FIX 4: linking the same alert twice must not create duplicate refs."""
    token = await analyst_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    await mongo_mock_db["anomaly_results"].insert_one(
        anomaly_doc(user_id="alice", risk_level="CRITICAL")
    )
    await async_client.post(
        f"{ALERTS_BASE}/generate", json={"limit": 100}, headers=headers
    )
    aid = (await async_client.get(f"{ALERTS_BASE}/", headers=headers)).json()["alerts"][0]["id"]

    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]

    for _ in range(3):
        r = await async_client.post(
            f"{INVESTIGATIONS_BASE}/{iid}/alerts",
            json={"alert_id": aid, "user_id": "alice"},
            headers=headers,
        )
        assert r.status_code == 200

    # Exactly one reference.
    inv = (await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}", headers=headers)).json()
    assert inv["related_alert_ids"] == [aid]


@pytest.mark.asyncio
async def test_unlink_alert_clears_both_sides(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    """FIX 4: DELETE /investigations/{id}/alerts/{aid} must clear BOTH sides."""
    token = await analyst_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    await mongo_mock_db["anomaly_results"].insert_one(
        anomaly_doc(user_id="alice", risk_level="CRITICAL")
    )
    await async_client.post(
        f"{ALERTS_BASE}/generate", json={"limit": 100}, headers=headers
    )
    aid = (await async_client.get(f"{ALERTS_BASE}/", headers=headers)).json()["alerts"][0]["id"]

    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]

    # Link then unlink.
    await async_client.post(
        f"{INVESTIGATIONS_BASE}/{iid}/alerts",
        json={"alert_id": aid, "user_id": "alice"},
        headers=headers,
    )
    r = await async_client.delete(
        f"{INVESTIGATIONS_BASE}/{iid}/alerts/{aid}",
        headers=headers,
    )
    assert r.status_code == 200

    alert = (await async_client.get(f"{ALERTS_BASE}/{aid}", headers=headers)).json()
    inv = (await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}", headers=headers)).json()
    # Both sides cleared.
    assert alert["investigation_id"] is None
    assert aid not in inv["related_alert_ids"]


@pytest.mark.asyncio
async def test_unlink_alert_when_not_linked_is_noop(
    async_client: AsyncClient, db_session: AsyncSession
):
    """FIX 4: unlinking an alert that is not linked is a 200 no-op."""
    token = await analyst_token(async_client, db_session)
    headers = {"Authorization": f"Bearer {token}"}

    r = await async_client.post(
        f"{INVESTIGATIONS_BASE}/",
        json={"title": "valid title", "severity": "HIGH"},
        headers=headers,
    )
    iid = r.json()["id"]

    aid = str(uuid.uuid4())
    r = await async_client.delete(
        f"{INVESTIGATIONS_BASE}/{iid}/alerts/{aid}",
        headers=headers,
    )
    assert r.status_code == 200
    inv = (await async_client.get(f"{INVESTIGATIONS_BASE}/{iid}", headers=headers)).json()
    assert aid not in inv["related_alert_ids"]
