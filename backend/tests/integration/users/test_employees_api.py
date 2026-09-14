"""
ITBIS — Integration tests: employee directory API and event attribution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.employees.application.directory_service import (
    detection_context,
    employee_resolver,
)
from app.modules.employees.infrastructure.repository import SQLEmployeeRepository
from app.modules.identity.domain.enums import RoleName
from tests.integration.users.test_user_admin_api import _create, _h

EMPLOYEES = "/api/v1/employees"

CERT_LDAP = (
    "employee_name,user_id,email,role,business_unit,functional_unit,department,team,supervisor\n"
    "Bevis Brady Sheppard,BBS0039,Bevis.Brady.Sheppard@dtaa.com,ITAdmin,1,5 - SalesAndMarketing,"
    "2 - Sales,3 - RegionalSales,Frances Alisa Wiggins\n"
    "Frances Alisa Wiggins,FAW0032,Frances.Alisa.Wiggins@dtaa.com,Manager,1,5 - SalesAndMarketing,"
    "2 - Sales,3 - RegionalSales,\n"
)


@pytest.fixture(autouse=True)
def _fresh_resolver():
    employee_resolver.forget()
    yield
    employee_resolver.forget()


async def _admin(client: AsyncClient, db: AsyncSession) -> str:
    _, token = await _create(client, db, "dir_admin", RoleName.ADMIN)
    return token


@pytest.mark.asyncio
async def test_permissions(async_client: AsyncClient, db_session: AsyncSession):
    _, viewer = await _create(async_client, db_session, "dir_viewer")
    _, analyst = await _create(async_client, db_session, "dir_analyst", RoleName.SECURITY_ANALYST)
    _, soc = await _create(async_client, db_session, "dir_soc", RoleName.SOC_ENGINEER)
    body = {"employee_id": "E1", "full_name": "Ann"}

    assert (await async_client.get(EMPLOYEES)).status_code == 401
    assert (await async_client.get(EMPLOYEES, headers=_h(viewer))).status_code == 403
    assert (await async_client.get(EMPLOYEES, headers=_h(analyst))).status_code == 200
    assert (await async_client.post(EMPLOYEES, json=body, headers=_h(analyst))).status_code == 403
    assert (await async_client.post(EMPLOYEES, json=body, headers=_h(soc))).status_code == 201


@pytest.mark.asyncio
async def test_create_link_and_conflicts(async_client: AsyncClient, db_session: AsyncSession):
    admin = await _admin(async_client, db_session)
    for eid, name in (("E100", "Vishwa K"), ("E200", "Sam Soc")):
        r = await async_client.post(
            EMPLOYEES,
            json={"employee_id": eid, "full_name": name, "department": "Security"},
            headers=_h(admin),
        )
        assert r.status_code == 201, r.text

    dup = await async_client.post(
        EMPLOYEES, json={"employee_id": "E100", "full_name": "x"}, headers=_h(admin)
    )
    linked = await async_client.post(
        f"{EMPLOYEES}/E100/accounts", json={"account": "VISHWA\\vishw"}, headers=_h(admin)
    )
    taken = await async_client.post(
        f"{EMPLOYEES}/E200/accounts", json={"account": "vishwa\\VISHW"}, headers=_h(admin)
    )
    device = await async_client.post(
        f"{EMPLOYEES}/E100/devices", json={"device_id": "WS-VISHWA"}, headers=_h(admin)
    )
    device_taken = await async_client.post(
        f"{EMPLOYEES}/E200/devices", json={"device_id": "WS-VISHWA"}, headers=_h(admin)
    )

    assert dup.status_code == 409
    assert linked.status_code == 201
    assert [a["account"] for a in linked.json()["accounts"]] == ["VISHWA\\vishw"]
    assert taken.status_code == 409, "accounts match case-insensitively"
    assert device.status_code == 201 and device_taken.status_code == 409

    account_id = linked.json()["accounts"][0]["id"]
    unlinked = await async_client.delete(
        f"{EMPLOYEES}/E100/accounts/{account_id}", headers=_h(admin)
    )
    assert unlinked.status_code == 200 and unlinked.json()["accounts"] == []
    assert (await async_client.get(f"{EMPLOYEES}/NOPE", headers=_h(admin))).status_code == 404

    patched = await async_client.patch(
        f"{EMPLOYEES}/E200", json={"status": "LEFT", "privileged": True}, headers=_h(admin)
    )
    assert patched.json()["status"] == "LEFT" and patched.json()["privileged"] is True


@pytest.mark.asyncio
async def test_cert_ldap_import_and_detection_facts(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin = await _admin(async_client, db_session)

    r = await async_client.post(
        f"{EMPLOYEES}/import",
        files={"file": ("ldap.csv", CERT_LDAP.encode(), "text/csv")},
        headers=_h(admin),
    )

    assert r.status_code == 200, r.text
    result = r.json()
    assert (result["format"], result["created"], result["accounts_linked"]) == ("cert_ldap", 2, 4)
    admin_employee = (await async_client.get(f"{EMPLOYEES}/BBS0039", headers=_h(admin))).json()
    assert admin_employee["privileged"] is True
    assert admin_employee["manager_employee_id"] == "FAW0032"
    assert admin_employee["job_title"] == "ITAdmin"

    again = await async_client.post(
        f"{EMPLOYEES}/import",
        files={"file": ("ldap.csv", CERT_LDAP.encode(), "text/csv")},
        headers=_h(admin),
    )
    assert (again.json()["created"], again.json()["updated"]) == (0, 2)

    await async_client.post(
        f"{EMPLOYEES}/FAW0032/devices", json={"device_id": "PC-5866"}, headers=_h(admin)
    )
    context = await detection_context(SQLEmployeeRepository(db_session))
    assert context.pc_owners == {"PC-5866": "FAW0032"}
    assert "BBS0039" in context.privileged_users

    bad = await async_client.post(
        f"{EMPLOYEES}/import",
        files={"file": ("x.csv", b"name,colour\na,b\n", "text/csv")},
        headers=_h(admin),
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_agent_events_are_attributed_and_unmapped_accounts_listed(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    admin = await _admin(async_client, db_session)
    await async_client.post(
        EMPLOYEES,
        json={"employee_id": "E100", "full_name": "Vishwa K", "department": "Security"},
        headers=_h(admin),
    )
    await async_client.post(
        f"{EMPLOYEES}/E100/accounts", json={"account": "VISHWA\\vishw"}, headers=_h(admin)
    )

    now = datetime.now(UTC)
    events = [
        {
            "event_type": "logon",
            "source_dataset": "win_endpoint",
            "user_id": "VISHWA\\vishw",
            "raw_event_id": "a1",
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
        },
        {
            "event_type": "logon",
            "source_dataset": "win_endpoint",
            "user_id": "CONTRACTOR\\bob",
            "raw_event_id": "a2",
            "timestamp": (now - timedelta(minutes=4)).isoformat(),
            "device_id": "WS-9",
        },
        {
            "event_type": "app_launch",
            "source_dataset": "win_endpoint",
            "user_id": "unknown",
            "raw_event_id": "a3",
            "timestamp": (now - timedelta(minutes=3)).isoformat(),
        },
    ]
    r = await async_client.post(
        "/api/v1/ingestion/events",
        json={"agent_id": "WS-VISHWA", "events": events},
        headers=_h(admin),
    )
    assert r.status_code == 200, r.text

    stored = {d["user_id"]: d async for d in mongo_mock_db["canonical_events"].find({})}
    assert stored["VISHWA\\vishw"]["employee_id"] == "E100"
    assert stored["VISHWA\\vishw"]["department"] == "Security"
    assert stored["CONTRACTOR\\bob"].get("employee_id") is None

    unmapped = (await async_client.get(f"{EMPLOYEES}/unmapped-accounts", headers=_h(admin))).json()
    assert [a["account"] for a in unmapped["accounts"]] == ["CONTRACTOR\\bob"]
    assert unmapped["accounts"][0]["devices"] == ["WS-9"]
