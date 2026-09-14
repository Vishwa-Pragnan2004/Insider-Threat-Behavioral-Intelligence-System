"""
ITBIS — Integration tests: access requests from the sign-in page.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.enums import RoleName
from tests.integration.users.test_user_admin_api import (
    AUTH,
    PASSWORD,
    USERS,
    _audit_rows,
    _create,
    _h,
    _login,
)

REQUESTS = f"{USERS}/access-requests"


def _body(username: str = "sam.soc", role: str = "SOC_ENGINEER", **extra) -> dict:
    return {
        "username": username,
        "email": f"{username}@example.com",
        "full_name": "Sam Soc",
        "password": PASSWORD,
        "requested_role": role,
        "reason": "I monitor endpoint telemetry on the night shift.",
        **extra,
    }


async def _attempt_login(client: AsyncClient, email: str):
    return await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})


@pytest.mark.asyncio
async def test_request_approve_then_sign_in(async_client: AsyncClient, db_session: AsyncSession):
    _, admin = await _create(async_client, db_session, "gate_admin", RoleName.ADMIN)

    submitted = await async_client.post(f"{AUTH}/access-requests", json=_body())
    assert submitted.status_code == 202, submitted.text
    assert submitted.json()["status"] == "PENDING"

    waiting = await _attempt_login(async_client, "sam.soc@example.com")
    assert waiting.status_code == 403
    assert waiting.json()["detail"] == "Your access request is awaiting administrator approval."
    wrong_password = await async_client.post(
        f"{AUTH}/login", json={"email": "sam.soc@example.com", "password": "Wrong1!pass"}
    )
    assert wrong_password.status_code == 401, "no status hints without the password"

    queue = (
        await async_client.get(REQUESTS, params={"status": "PENDING"}, headers=_h(admin))
    ).json()
    assert queue["pending"] == 1
    [item] = queue["requests"]
    assert (item["username"], item["requested_role"]) == ("sam.soc", "SOC_ENGINEER")

    approved = await async_client.post(
        f"{REQUESTS}/{item['id']}/approve",
        json={"roles": ["SOC_ENGINEER", "SECURITY_ANALYST"]},
        headers=_h(admin),
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "APPROVED" and body["decided_by"] == "gate_admin"
    assert sorted(body["granted_roles"]) == ["SECURITY_ANALYST", "SOC_ENGINEER"]

    token = await _login(async_client, "sam.soc@example.com")
    me = (await async_client.get(f"{AUTH}/me", headers=_h(token))).json()
    assert {"dashboard:soc", "dashboard:analyst"} <= set(me["permissions"])

    again = await async_client.post(f"{REQUESTS}/{item['id']}/reject", json={}, headers=_h(admin))
    assert again.status_code == 409
    [row] = await _audit_rows(db_session, "ACCESS_REQUEST_APPROVED")
    assert row.details == "requested SOC_ENGINEER; granted SECURITY_ANALYST, SOC_ENGINEER"


@pytest.mark.asyncio
async def test_rejected_requester_is_told_and_stays_locked(
    async_client: AsyncClient, db_session: AsyncSession
):
    _, admin = await _create(async_client, db_session, "no_admin", RoleName.ADMIN)
    await async_client.post(f"{AUTH}/access-requests", json=_body("mia.mgr", "SECURITY_MANAGER"))
    [item] = (await async_client.get(REQUESTS, headers=_h(admin))).json()["requests"]

    rejected = await async_client.post(
        f"{REQUESTS}/{item['id']}/reject", json={"note": "Not on the team"}, headers=_h(admin)
    )

    assert rejected.status_code == 200 and rejected.json()["decision_note"] == "Not on the team"
    login = await _attempt_login(async_client, "mia.mgr@example.com")
    assert login.status_code == 403
    assert "declined" in login.json()["detail"]


@pytest.mark.asyncio
async def test_request_validation(async_client: AsyncClient, db_session: AsyncSession):
    await _create(async_client, db_session, "taken_name")

    admin_role = await async_client.post(f"{AUTH}/access-requests", json=_body(role="ADMIN"))
    duplicate = await async_client.post(f"{AUTH}/access-requests", json=_body("taken_name"))
    weak = await async_client.post(
        f"{AUTH}/access-requests", json=_body("weak.pw", password="password")
    )
    short_reason = await async_client.post(
        f"{AUTH}/access-requests", json=_body("short.reason", reason="pls")
    )

    assert admin_role.status_code == 422
    assert duplicate.status_code == 409
    assert weak.status_code == 422
    assert short_reason.status_code == 422


@pytest.mark.asyncio
async def test_only_administrators_decide(async_client: AsyncClient, db_session: AsyncSession):
    _, analyst = await _create(async_client, db_session, "ana_lyst", RoleName.SECURITY_ANALYST)
    _, admin = await _create(async_client, db_session, "dec_admin", RoleName.ADMIN)
    await async_client.post(f"{AUTH}/access-requests", json=_body("viewer.req", "VIEWER"))
    [item] = (await async_client.get(REQUESTS, headers=_h(admin))).json()["requests"]

    assert (await async_client.get(REQUESTS)).status_code == 401
    assert (await async_client.get(REQUESTS, headers=_h(analyst))).status_code == 200
    denied = await async_client.post(
        f"{REQUESTS}/{item['id']}/approve", json={"roles": ["ADMIN"]}, headers=_h(analyst)
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_sign_in_with_username_ignoring_case(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Regression: typing the username ("ADAM") into sign-in failed with a bare 422."""
    _, admin = await _create(async_client, db_session, "case_admin", RoleName.ADMIN)
    await async_client.post(f"{AUTH}/access-requests", json=_body("adam", "SECURITY_ANALYST"))

    pending = await _attempt_login(async_client, "ADAM")
    assert pending.status_code == 403, "the waiting message works by username too"

    [item] = (await async_client.get(REQUESTS, headers=_h(admin))).json()["requests"]
    await async_client.post(
        f"{REQUESTS}/{item['id']}/approve", json={"roles": ["SECURITY_ANALYST"]}, headers=_h(admin)
    )

    for identifier in ("ADAM", "adam", "Adam@Example.com"):
        r = await _attempt_login(async_client, identifier)
        assert r.status_code == 200, (identifier, r.text)
    unknown = await _attempt_login(async_client, "nobody")
    assert unknown.status_code == 401
