"""
ITBIS — Unit tests: access requests (submit, approve, reject), with in-memory fakes.
"""

from __future__ import annotations

import uuid

import pytest

from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import RoleName
from app.modules.users.application.access_request_service import (
    ACCESS_APPROVED,
    ACCESS_REJECTED,
    ACCESS_REQUESTED,
    AccessRequestDecidedError,
    AccessRequestNotFoundError,
    AccessRequestService,
    RoleNotRequestableError,
)
from app.modules.users.application.user_admin_service import (
    DuplicateUserError,
    InvalidPasswordError,
)
from app.modules.users.domain.access_request import AccessRequestStatus, AccessRequestView

ROLES = {name: Role(id=uuid.uuid4(), name=name, permissions=[]) for name in RoleName}
PASSWORD = "SecurePass1!"


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
    async def get_by_name(self, name):
        return ROLES[name]


class FakeRequests:
    def __init__(self, users: FakeUsers) -> None:
        self.users = users
        self.by_id = {}

    async def add(self, request):
        self.by_id[request.id] = request

    async def get(self, request_id):
        return self.by_id.get(request_id)

    async def save(self, request):
        self.by_id[request.id] = request

    async def list_views(self, status=None):
        return [
            AccessRequestView(
                request=r,
                username=self.users.by_id[r.user_id].username,
                email=self.users.by_id[r.user_id].email,
                full_name="",
            )
            for r in self.by_id.values()
            if status is None or r.status == status
        ]

    async def get_view(self, request_id):
        return None

    async def count(self, status):
        return sum(1 for r in self.by_id.values() if r.status == status)


class FakeAudit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kwargs):
        self.records.append(kwargs)


def _admin() -> User:
    return User(
        id=uuid.uuid4(),
        username="admin",
        email="admin@example.com",
        hashed_password="x",
        roles=[ROLES[RoleName.ADMIN]],
    )


def _service():
    admin = _admin()
    users = FakeUsers(admin)
    requests = FakeRequests(users)
    audit = FakeAudit()
    service = AccessRequestService(users=users, roles=FakeRoles(), requests=requests, audit=audit)
    return service, admin, users, requests, audit


async def _submit(service, **overrides):
    fields = {
        "username": "sam.soc",
        "email": "Sam.Soc@Example.com",
        "full_name": " Sam Soc ",
        "password": PASSWORD,
        "requested_role": RoleName.SOC_ENGINEER,
        "reason": "  I run the night shift in the SOC.  ",
    }
    return await service.submit(**{**fields, **overrides})


# ─── Submit ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submitting_creates_a_locked_account_without_roles():
    service, _, users, _, audit = _service()

    request = await _submit(service)

    user = users.by_id[request.user_id]
    assert (user.email, user.full_name) == ("sam.soc@example.com", "Sam Soc")
    assert user.is_active is False and user.roles == []
    assert user.hashed_password != PASSWORD
    assert request.status == AccessRequestStatus.PENDING
    assert request.reason == "I run the night shift in the SOC."
    [entry] = audit.records
    assert entry["event_type"] == ACCESS_REQUESTED and entry["actor"] is user


@pytest.mark.asyncio
async def test_administrator_access_cannot_be_requested():
    service, _, users, _, _ = _service()
    with pytest.raises(RoleNotRequestableError):
        await _submit(service, requested_role=RoleName.ADMIN)
    assert len(users.by_id) == 1


@pytest.mark.asyncio
async def test_duplicates_and_weak_passwords_are_refused():
    service, _, _, _, _ = _service()
    with pytest.raises(DuplicateUserError):
        await _submit(service, email="admin@example.com")
    with pytest.raises(DuplicateUserError):
        await _submit(service, username="admin")
    with pytest.raises(InvalidPasswordError):
        await _submit(service, password="password")


# ─── Decide ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approval_grants_the_chosen_roles_and_unlocks_the_account():
    service, admin, users, _, audit = _service()
    request = await _submit(service)

    decided = await service.approve(
        admin, request.id, [RoleName.SECURITY_ANALYST, RoleName.SOC_ENGINEER]
    )

    user = users.by_id[request.user_id]
    assert user.is_active
    assert sorted(r.name.value for r in user.roles) == ["SECURITY_ANALYST", "SOC_ENGINEER"]
    assert decided.status == AccessRequestStatus.APPROVED
    assert decided.decided_by == admin.id and decided.decided_at is not None
    assert decided.granted_roles == [RoleName.SECURITY_ANALYST, RoleName.SOC_ENGINEER]
    assert audit.records[-1]["event_type"] == ACCESS_APPROVED
    assert audit.records[-1]["details"] == (
        "requested SOC_ENGINEER; granted SECURITY_ANALYST, SOC_ENGINEER"
    )


@pytest.mark.asyncio
async def test_rejection_keeps_the_account_locked():
    service, admin, users, _, audit = _service()
    request = await _submit(service)

    decided = await service.reject(admin, request.id, "  Not in the security team  ")

    assert users.by_id[request.user_id].is_active is False
    assert decided.status == AccessRequestStatus.REJECTED
    assert decided.decision_note == "Not in the security team"
    assert audit.records[-1]["event_type"] == ACCESS_REJECTED


@pytest.mark.asyncio
async def test_a_request_is_decided_only_once():
    service, admin, _, _, _ = _service()
    request = await _submit(service)
    await service.reject(admin, request.id)

    with pytest.raises(AccessRequestDecidedError):
        await service.approve(admin, request.id, [RoleName.VIEWER])
    with pytest.raises(AccessRequestNotFoundError):
        await service.reject(admin, uuid.uuid4())


@pytest.mark.asyncio
async def test_listing_reports_the_pending_count():
    service, admin, _, _, _ = _service()
    first = await _submit(service)
    await _submit(
        service,
        username="mia.mgr",
        email="mia@example.com",
        requested_role=RoleName.SECURITY_MANAGER,
    )
    await service.approve(admin, first.id, [RoleName.SOC_ENGINEER])

    pending_views, pending = await service.list_requests(AccessRequestStatus.PENDING)
    all_views, _ = await service.list_requests()

    assert [v.username for v in pending_views] == ["mia.mgr"]
    assert pending == 1 and len(all_views) == 2
