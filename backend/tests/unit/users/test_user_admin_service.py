"""
ITBIS — Unit tests: user and role administration service (lockout guards,
session revocation, auditing), with in-memory fakes.
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import RoleName
from app.modules.users.application.user_admin_service import (
    ACCOUNT_DISABLED,
    ACCOUNT_ENABLED,
    ROLES_CHANGED,
    USER_CREATED,
    AdminLockoutError,
    DuplicateUserError,
    InvalidPasswordError,
    UnknownRoleError,
    UserAdminService,
    UserNotFoundError,
)

ROLES = {name: Role(id=uuid.uuid4(), name=name, permissions=[]) for name in RoleName}


def _user(name: str, *roles: RoleName, active: bool = True, superadmin: bool = False) -> User:
    return User(
        id=uuid.uuid4(),
        username=name,
        email=f"{name}@example.com",
        hashed_password="x",
        is_active=active,
        is_superadmin=superadmin,
        roles=[ROLES[r] for r in roles],
    )


class FakeUsers:
    def __init__(self, *users: User) -> None:
        self.by_id = {u.id: u for u in users}

    async def get_by_id(self, user_id):
        return self.by_id.get(user_id)

    async def save(self, user):
        self.by_id[user.id] = user
        return user

    async def exists_by_email(self, email):
        return any(u.email == email for u in self.by_id.values())

    async def exists_by_username(self, username):
        return any(u.username == username for u in self.by_id.values())


class FakeRoles:
    def __init__(self, missing: set[RoleName] | None = None) -> None:
        self.missing = missing or set()

    async def get_by_name(self, name):
        return None if name in self.missing else ROLES[name]

    async def get_all(self):
        return [ROLES[n] for n in reversed(list(RoleName)) if n not in self.missing]


class FakeQueries:
    def __init__(self, users: FakeUsers, active_admins: int | None = None) -> None:
        self.users = users
        self.override = active_admins

    async def list_users(self, **kwargs):
        users = list(self.users.by_id.values())
        return users, len(users)

    async def count_active_admins(self):
        if self.override is not None:
            return self.override
        return sum(
            1
            for u in self.users.by_id.values()
            if u.is_active and (u.is_superadmin or u.has_role(RoleName.ADMIN))
        )


class FakeSessions:
    def __init__(self, fail: bool = False) -> None:
        self.revoked: list[str] = []
        self.fail = fail

    async def revoke_all_for_user(self, user_id):
        if self.fail:
            raise ConnectionError("redis down")
        self.revoked.append(user_id)


class FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kwargs):
        self.records.append(kwargs)


def _service(*users: User, active_admins: int | None = None, sessions=None, roles=None):
    repo = FakeUsers(*users)
    audit = FakeAudit()
    sessions = sessions or FakeSessions()
    service = UserAdminService(
        users=repo,
        roles=roles or FakeRoles(),
        queries=FakeQueries(repo, active_admins),
        sessions=sessions,
        audit=audit,
    )
    return service, audit, sessions


# ─── Roles ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_roles_replaces_them_and_audits_before_and_after():
    admin = _user("admin", RoleName.ADMIN)
    viewer = _user("viewer", RoleName.VIEWER)
    service, audit, _ = _service(admin, viewer)

    saved = await service.set_roles(admin, viewer.id, [RoleName.SECURITY_ANALYST])

    assert [r.name for r in saved.roles] == [RoleName.SECURITY_ANALYST]
    [entry] = audit.records
    assert entry["event_type"] == ROLES_CHANGED
    assert entry["success"] is True
    assert entry["actor"] is admin
    assert entry["details"] == "roles: VIEWER -> SECURITY_ANALYST"


@pytest.mark.asyncio
async def test_duplicate_roles_collapse():
    admin = _user("admin", RoleName.ADMIN)
    viewer = _user("viewer", RoleName.VIEWER)
    service, _, _ = _service(admin, viewer)

    saved = await service.set_roles(
        admin, viewer.id, [RoleName.INVESTIGATOR, RoleName.INVESTIGATOR, RoleName.VIEWER]
    )

    assert sorted(r.name.value for r in saved.roles) == ["INVESTIGATOR", "VIEWER"]


@pytest.mark.asyncio
async def test_removing_your_own_admin_role_is_refused_and_audited():
    admin = _user("admin", RoleName.ADMIN)
    other_admin = _user("other", RoleName.ADMIN)
    service, audit, _ = _service(admin, other_admin)

    with pytest.raises(AdminLockoutError, match="your own ADMIN role"):
        await service.set_roles(admin, admin.id, [RoleName.VIEWER])

    assert admin.has_role(RoleName.ADMIN), "nothing changed"
    [entry] = audit.records
    assert entry["success"] is False
    assert "your own ADMIN role" in entry["failure_reason"]


@pytest.mark.asyncio
async def test_demoting_the_last_active_admin_is_refused():
    actor = _user("actor", RoleName.ADMIN)
    last_admin = _user("last", RoleName.ADMIN)
    service, _, _ = _service(actor, last_admin, active_admins=1)

    with pytest.raises(AdminLockoutError, match="last active administrator"):
        await service.set_roles(actor, last_admin.id, [RoleName.VIEWER])


@pytest.mark.asyncio
async def test_demoting_one_of_several_admins_is_allowed():
    actor = _user("actor", RoleName.ADMIN)
    other = _user("other", RoleName.ADMIN)
    service, _, _ = _service(actor, other)

    saved = await service.set_roles(actor, other.id, [RoleName.INVESTIGATOR])

    assert not saved.has_role(RoleName.ADMIN)


@pytest.mark.asyncio
async def test_superadmin_without_the_admin_role_is_not_a_lockout():
    superadmin = _user("root", RoleName.ADMIN, superadmin=True)
    service, _, _ = _service(superadmin, active_admins=1)

    saved = await service.set_roles(superadmin, superadmin.id, [RoleName.VIEWER])

    assert saved.is_superadmin, "still has administrator access through the flag"


@pytest.mark.asyncio
async def test_unknown_role_and_unknown_user():
    admin = _user("admin", RoleName.ADMIN)
    viewer = _user("viewer", RoleName.VIEWER)
    service, _, _ = _service(admin, viewer, roles=FakeRoles(missing={RoleName.INVESTIGATOR}))

    with pytest.raises(UnknownRoleError):
        await service.set_roles(admin, viewer.id, [RoleName.INVESTIGATOR])
    with pytest.raises(UserNotFoundError):
        await service.set_roles(admin, uuid.uuid4(), [RoleName.VIEWER])


@pytest.mark.asyncio
async def test_roles_are_listed_in_enum_order():
    service, _, _ = _service()
    assert [r.name for r in await service.list_roles()] == list(RoleName)


# ─── Disable / enable ───────────────────────────────────────


@pytest.mark.asyncio
async def test_disabling_revokes_sessions_and_audits():
    admin = _user("admin", RoleName.ADMIN)
    viewer = _user("viewer", RoleName.VIEWER)
    service, audit, sessions = _service(admin, viewer)

    saved = await service.disable(admin, viewer.id)

    assert saved.is_active is False
    assert sessions.revoked == [str(viewer.id)]
    [entry] = audit.records
    assert entry["event_type"] == ACCOUNT_DISABLED
    assert entry["details"] == "account disabled; refresh tokens revoked"


@pytest.mark.asyncio
async def test_disabling_yourself_is_refused():
    admin = _user("admin", RoleName.ADMIN)
    service, audit, _ = _service(admin, _user("other", RoleName.ADMIN))

    with pytest.raises(AdminLockoutError, match="your own account"):
        await service.disable(admin, admin.id)

    assert admin.is_active
    assert audit.records[0]["success"] is False


@pytest.mark.asyncio
async def test_disabling_the_last_active_admin_is_refused():
    actor = _user("actor", RoleName.ADMIN)
    last_admin = _user("last", RoleName.ADMIN)
    service, _, _ = _service(actor, last_admin, active_admins=1)

    with pytest.raises(AdminLockoutError, match="last active administrator"):
        await service.disable(actor, last_admin.id)


@pytest.mark.asyncio
async def test_disabling_a_non_admin_never_consults_the_admin_count():
    admin = _user("admin", RoleName.ADMIN)
    viewer = _user("viewer", RoleName.VIEWER)
    service, _, _ = _service(admin, viewer, active_admins=1)

    assert (await service.disable(admin, viewer.id)).is_active is False


@pytest.mark.asyncio
async def test_disable_still_succeeds_when_redis_is_down():
    admin = _user("admin", RoleName.ADMIN)
    viewer = _user("viewer", RoleName.VIEWER)
    service, audit, _ = _service(admin, viewer, sessions=FakeSessions(fail=True))

    saved = await service.disable(admin, viewer.id)

    assert saved.is_active is False
    assert "could NOT be revoked" in audit.records[0]["details"]


@pytest.mark.asyncio
async def test_disable_and_enable_are_idempotent():
    admin = _user("admin", RoleName.ADMIN)
    disabled = _user("gone", RoleName.VIEWER, active=False)
    service, audit, sessions = _service(admin, disabled)

    await service.disable(admin, disabled.id)
    assert sessions.revoked == [] and audit.records == []

    enabled = await service.enable(admin, disabled.id)
    await service.enable(admin, disabled.id)
    assert enabled.is_active
    assert [r["event_type"] for r in audit.records] == [ACCOUNT_ENABLED]


# ─── Create ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_creates_a_soc_engineer():
    admin = _user("admin", RoleName.ADMIN)
    service, audit, _ = _service(admin)

    user = await service.create_user(
        admin,
        username="soc.eng",
        email="SOC.Eng@Example.com",
        password="SecurePass1!",
        role_names=[RoleName.SOC_ENGINEER, RoleName.SOC_ENGINEER],
        full_name="  Sam Engineer ",
    )

    assert user.email == "soc.eng@example.com"
    assert user.full_name == "Sam Engineer"
    assert user.is_active and user.is_verified
    assert [r.name for r in user.roles] == [RoleName.SOC_ENGINEER]
    assert user.hashed_password != "SecurePass1!"
    [entry] = audit.records
    assert entry["event_type"] == USER_CREATED
    assert entry["details"] == "account created with roles: SOC_ENGINEER"


@pytest.mark.asyncio
async def test_duplicate_email_or_username_is_refused():
    admin = _user("admin", RoleName.ADMIN)
    service, _, _ = _service(admin)

    with pytest.raises(DuplicateUserError, match="email"):
        await service.create_user(
            admin, username="new", email="admin@example.com",
            password="SecurePass1!", role_names=[RoleName.VIEWER],
        )
    with pytest.raises(DuplicateUserError, match="username"):
        await service.create_user(
            admin, username="admin", email="new@example.com",
            password="SecurePass1!", role_names=[RoleName.VIEWER],
        )


@pytest.mark.asyncio
async def test_weak_password_and_unknown_role_create_nothing():
    admin = _user("admin", RoleName.ADMIN)
    service, audit, _ = _service(admin, roles=FakeRoles(missing={RoleName.SECURITY_MANAGER}))

    with pytest.raises(InvalidPasswordError):
        await service.create_user(
            admin, username="weak", email="weak@example.com",
            password="password", role_names=[RoleName.VIEWER],
        )
    with pytest.raises(UnknownRoleError):
        await service.create_user(
            admin, username="boss", email="boss@example.com",
            password="SecurePass1!", role_names=[RoleName.SECURITY_MANAGER],
        )
    assert len(service._users.by_id) == 1 and audit.records == []


def test_each_spec_role_gets_its_own_dashboard():
    from app.modules.identity.domain.enums import ROLE_PERMISSIONS, PermissionName

    assert PermissionName.DASHBOARD_ANALYST in ROLE_PERMISSIONS[RoleName.SECURITY_ANALYST]
    assert PermissionName.DASHBOARD_SOC in ROLE_PERMISSIONS[RoleName.SOC_ENGINEER]
    assert PermissionName.DASHBOARD_MANAGER in ROLE_PERMISSIONS[RoleName.SECURITY_MANAGER]
    manager = ROLE_PERMISSIONS[RoleName.SECURITY_MANAGER]
    assert PermissionName.ALERTS_UPDATE not in manager, "managers oversee; they don't triage"

