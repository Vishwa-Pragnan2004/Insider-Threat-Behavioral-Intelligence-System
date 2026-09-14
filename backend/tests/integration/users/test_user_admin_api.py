"""
ITBIS — Integration tests: user and role administration API.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.models import AuthAuditLogModel
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)

AUTH = "/api/v1/auth"
USERS = "/api/v1/users"
PASSWORD = "SecurePass1!"


async def _create(
    client: AsyncClient, db: AsyncSession, username: str, role: RoleName | None = None
) -> tuple[str, str]:
    """Register a user (VIEWER by default), optionally add a role; return (id, token)."""
    email = f"{username}@example.com"
    r = await client.post(
        f"{AUTH}/register",
        json={"username": username, "email": email, "password": PASSWORD, "full_name": username},
    )
    assert r.status_code == 201, r.text
    users, roles = SQLUserRepository(db), SQLRoleRepository(db)
    user = await users.get_by_email(email)
    if role is not None:
        user.assign_role(await roles.get_by_name(role))
        await users.save(user)
        await db.commit()
    return str(user.id), await _login(client, email)


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post(f"{AUTH}/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _audit_rows(db: AsyncSession, event_type: str) -> list[AuthAuditLogModel]:
    result = await db.execute(
        select(AuthAuditLogModel).where(AuthAuditLogModel.event_type == event_type)
    )
    return list(result.scalars().all())


# ─── Access control ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_requires_authentication(async_client: AsyncClient):
    assert (await async_client.get(USERS)).status_code == 401


@pytest.mark.asyncio
async def test_viewer_can_list_users_but_not_change_them(
    async_client: AsyncClient, db_session: AsyncSession
):
    viewer_id, viewer = await _create(async_client, db_session, "plain_viewer")

    assert (await async_client.get(USERS, headers=_h(viewer))).status_code == 200
    r = await async_client.put(
        f"{USERS}/{viewer_id}/roles", json={"roles": ["ADMIN"]}, headers=_h(viewer)
    )
    assert r.status_code == 403, "no self-promotion"


# ─── Reads ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_lists_and_filters_users(async_client: AsyncClient, db_session: AsyncSession):
    _, admin = await _create(async_client, db_session, "ops_admin", RoleName.ADMIN)
    await _create(async_client, db_session, "soc_analyst", RoleName.SECURITY_ANALYST)
    await _create(async_client, db_session, "jane_viewer")

    everyone = (await async_client.get(USERS, headers=_h(admin))).json()
    analysts = (
        await async_client.get(USERS, params={"role": "SECURITY_ANALYST"}, headers=_h(admin))
    ).json()
    search = (await async_client.get(USERS, params={"search": "jane"}, headers=_h(admin))).json()

    assert everyone["total"] >= 3
    assert [u["username"] for u in analysts["users"]] == ["soc_analyst"]
    assert [u["username"] for u in search["users"]] == ["jane_viewer"]
    assert "hashed_password" not in everyone["users"][0]


@pytest.mark.asyncio
async def test_roles_catalogue(async_client: AsyncClient, db_session: AsyncSession):
    _, admin = await _create(async_client, db_session, "cat_admin", RoleName.ADMIN)

    roles = (await async_client.get(f"{USERS}/roles", headers=_h(admin))).json()

    assert [r["name"] for r in roles] == [r.value for r in RoleName]
    admin_role = next(r for r in roles if r["name"] == "ADMIN")
    assert "users:update" in admin_role["permissions"]


# ─── Role changes ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_promotion_takes_effect_and_is_audited(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin_id, admin = await _create(async_client, db_session, "promo_admin", RoleName.ADMIN)
    viewer_id, _ = await _create(async_client, db_session, "promo_viewer")

    r = await async_client.put(
        f"{USERS}/{viewer_id}/roles", json={"roles": ["SECURITY_ANALYST"]}, headers=_h(admin)
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["roles"] == ["SECURITY_ANALYST"]
    assert "alerts:create" in body["permissions"]

    fresh = await _login(async_client, "promo_viewer@example.com")
    me = (await async_client.get(f"{AUTH}/me", headers=_h(fresh))).json()
    assert "alerts:create" in me["permissions"]

    [row] = await _audit_rows(db_session, "USER_ROLES_CHANGED")
    assert str(row.actor_user_id) == admin_id
    assert str(row.user_id) == viewer_id
    assert row.success is True
    assert row.details == "roles: VIEWER -> SECURITY_ANALYST"


@pytest.mark.asyncio
async def test_unknown_user_and_invalid_role(async_client: AsyncClient, db_session: AsyncSession):
    _, admin = await _create(async_client, db_session, "err_admin", RoleName.ADMIN)
    viewer_id, _ = await _create(async_client, db_session, "err_viewer")

    missing = await async_client.put(
        f"{USERS}/00000000-0000-0000-0000-000000000000/roles",
        json={"roles": ["VIEWER"]},
        headers=_h(admin),
    )
    bogus = await async_client.put(
        f"{USERS}/{viewer_id}/roles", json={"roles": ["OVERLORD"]}, headers=_h(admin)
    )
    empty = await async_client.put(f"{USERS}/{viewer_id}/roles", json={"roles": []}, headers=_h(admin))

    assert missing.status_code == 404
    assert bogus.status_code == 422
    assert empty.status_code == 422


# ─── Disable / enable ───────────────────────────────────────


@pytest.mark.asyncio
async def test_disabling_locks_the_user_out_immediately(
    async_client: AsyncClient, db_session: AsyncSession
):
    _, admin = await _create(async_client, db_session, "lock_admin", RoleName.ADMIN)
    viewer_id, viewer_token = await _create(async_client, db_session, "lock_viewer")
    assert (await async_client.get(USERS, headers=_h(viewer_token))).status_code == 200

    r = await async_client.post(f"{USERS}/{viewer_id}/disable", headers=_h(admin))
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    assert (await async_client.get(USERS, headers=_h(viewer_token))).status_code == 401
    login = await async_client.post(
        f"{AUTH}/login", json={"email": "lock_viewer@example.com", "password": PASSWORD}
    )
    assert login.status_code == 401
    [row] = await _audit_rows(db_session, "ACCOUNT_DISABLED")
    assert row.success is True

    r = await async_client.post(f"{USERS}/{viewer_id}/enable", headers=_h(admin))
    assert r.status_code == 200
    await _login(async_client, "lock_viewer@example.com")


@pytest.mark.asyncio
async def test_admin_cannot_lock_themselves_out(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin_id, admin = await _create(async_client, db_session, "self_admin", RoleName.ADMIN)

    disable = await async_client.post(f"{USERS}/{admin_id}/disable", headers=_h(admin))
    demote = await async_client.put(
        f"{USERS}/{admin_id}/roles", json={"roles": ["VIEWER"]}, headers=_h(admin)
    )

    assert disable.status_code == 409
    assert demote.status_code == 409
    assert (await async_client.get(USERS, headers=_h(admin))).status_code == 200, "still an admin"

    refusals = await _audit_rows(db_session, "ACCOUNT_DISABLED") + await _audit_rows(
        db_session, "USER_ROLES_CHANGED"
    )
    assert len(refusals) == 2
    assert all(row.success is False and row.failure_reason for row in refusals)


# ─── Create ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_creates_users_with_spec_roles(
    async_client: AsyncClient, db_session: AsyncSession
):
    _, admin = await _create(async_client, db_session, "create_admin", RoleName.ADMIN)

    for username, role, dashboard in [
        ("ana.analyst", "SECURITY_ANALYST", "dashboard:analyst"),
        ("sam.soc", "SOC_ENGINEER", "dashboard:soc"),
        ("mia.manager", "SECURITY_MANAGER", "dashboard:manager"),
    ]:
        r = await async_client.post(
            USERS,
            json={
                "username": username,
                "email": f"{username}@example.com",
                "full_name": username,
                "password": PASSWORD,
                "roles": [role],
            },
            headers=_h(admin),
        )
        assert r.status_code == 201, r.text
        assert r.json()["roles"] == [role]

        token = await _login(async_client, f"{username}@example.com")
        me = (await async_client.get(f"{AUTH}/me", headers=_h(token))).json()
        assert dashboard in me["permissions"]

    [row, *_] = await _audit_rows(db_session, "USER_CREATED")
    assert row.success is True


@pytest.mark.asyncio
async def test_create_user_validation_and_access(
    async_client: AsyncClient, db_session: AsyncSession
):
    _, admin = await _create(async_client, db_session, "val_admin", RoleName.ADMIN)
    _, analyst = await _create(async_client, db_session, "val_analyst", RoleName.SECURITY_ANALYST)
    body = {
        "username": "dupe.user",
        "email": "dupe.user@example.com",
        "password": PASSWORD,
        "roles": ["VIEWER"],
    }

    assert (await async_client.post(USERS, json=body, headers=_h(analyst))).status_code == 403
    assert (await async_client.post(USERS, json=body, headers=_h(admin))).status_code == 201
    assert (await async_client.post(USERS, json=body, headers=_h(admin))).status_code == 409
    weak = {**body, "username": "weak.user", "email": "weak@example.com", "password": "password"}
    assert (await async_client.post(USERS, json=weak, headers=_h(admin))).status_code == 422
    no_roles = {**body, "username": "nobody", "email": "nobody@example.com", "roles": []}
    assert (await async_client.post(USERS, json=no_roles, headers=_h(admin))).status_code == 422

