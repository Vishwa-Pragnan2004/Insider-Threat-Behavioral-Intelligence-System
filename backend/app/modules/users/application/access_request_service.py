"""
ITBIS — Users Module: access requests

Self-service onboarding without self-service privileges:

  1. Someone submits a request from the sign-in page: their details, the role
     they need and why. An account is created, disabled and without roles.
  2. Signing in tells them the request is still waiting (or was declined).
  3. An administrator approves it, choosing the roles actually granted, which
     enables the account; or rejects it, which leaves it disabled.

Every step is written to the audit log.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from app.modules.identity.application.services.password_service import password_service
from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import RoleName
from app.modules.identity.domain.exceptions import WeakPasswordError
from app.modules.identity.domain.repositories import IRoleRepository, IUserRepository
from app.modules.users.application.user_admin_service import (
    AdminAuditLog,
    AuditContext,
    DuplicateUserError,
    InvalidPasswordError,
    UnknownRoleError,
    UserAdminError,
    UserNotFoundError,
)
from app.modules.users.domain.access_request import (
    REQUESTABLE_ROLES,
    AccessRequest,
    AccessRequestStatus,
    AccessRequestView,
)

ACCESS_REQUESTED = "ACCESS_REQUESTED"
ACCESS_APPROVED = "ACCESS_REQUEST_APPROVED"
ACCESS_REJECTED = "ACCESS_REQUEST_REJECTED"


class AccessRequestNotFoundError(UserAdminError):
    """No access request with that ID."""


class AccessRequestDecidedError(UserAdminError):
    """The request was already approved or rejected."""


class RoleNotRequestableError(UserAdminError):
    """Administrator access can't be requested."""


class AccessRequestStore(Protocol):
    async def add(self, request: AccessRequest) -> None: ...

    async def get(self, request_id: uuid.UUID) -> AccessRequest | None: ...

    async def save(self, request: AccessRequest) -> None: ...

    async def list_views(
        self, status: AccessRequestStatus | None = None
    ) -> list[AccessRequestView]: ...

    async def get_view(self, request_id: uuid.UUID) -> AccessRequestView | None: ...

    async def count(self, status: AccessRequestStatus) -> int: ...


class AccessRequestService:
    def __init__(
        self,
        *,
        users: IUserRepository,
        roles: IRoleRepository,
        requests: AccessRequestStore,
        audit: AdminAuditLog,
    ) -> None:
        self._users = users
        self._roles = roles
        self._requests = requests
        self._audit = audit

    async def submit(
        self,
        *,
        username: str,
        email: str,
        full_name: str,
        password: str,
        requested_role: RoleName,
        reason: str,
        context: AuditContext | None = None,
    ) -> AccessRequest:
        if requested_role not in REQUESTABLE_ROLES:
            raise RoleNotRequestableError(
                "Administrator access can't be requested; ask an existing administrator."
            )
        username, email = username.strip(), email.strip().lower()
        if await self._users.exists_by_email(email):
            raise DuplicateUserError("That email is already registered.")
        if await self._users.exists_by_username(username):
            raise DuplicateUserError("That username is already taken.")
        try:
            hashed = password_service.hash(password)
        except WeakPasswordError as exc:
            raise InvalidPasswordError(str(exc)) from exc

        user = await self._users.save(
            User(
                id=uuid.uuid4(),
                username=username,
                email=email,
                hashed_password=hashed,
                full_name=full_name.strip(),
                is_active=False,
                is_verified=False,
            )
        )
        request = AccessRequest(
            user_id=user.id, requested_role=requested_role, reason=reason.strip()
        )
        await self._requests.add(request)
        await self._audit.record(
            event_type=ACCESS_REQUESTED,
            actor=user,
            target=user,
            success=True,
            details=f"requested role: {requested_role.value}",
            context=context,
        )
        return request

    async def list_requests(
        self, status: AccessRequestStatus | None = None
    ) -> tuple[list[AccessRequestView], int]:
        """The requests (newest first) and how many are still pending overall."""
        views = await self._requests.list_views(status)
        return views, await self._requests.count(AccessRequestStatus.PENDING)

    async def approve(
        self,
        actor: User,
        request_id: uuid.UUID,
        role_names: list[RoleName],
        *,
        context: AuditContext | None = None,
    ) -> AccessRequest:
        request = await self._pending(request_id)
        user = await self._requester(request)
        roles = await self._resolve_roles(role_names)

        user.set_roles(roles)
        user.enable()
        saved = await self._users.save(user)
        request.approve(actor.id, [role.name for role in roles])
        await self._requests.save(request)
        granted = ", ".join(sorted(role.name.value for role in roles))
        await self._audit.record(
            event_type=ACCESS_APPROVED,
            actor=actor,
            target=saved,
            success=True,
            details=f"requested {request.requested_role.value}; granted {granted}",
            context=context,
        )
        return request

    async def reject(
        self,
        actor: User,
        request_id: uuid.UUID,
        note: str | None = None,
        *,
        context: AuditContext | None = None,
    ) -> AccessRequest:
        request = await self._pending(request_id)
        user = await self._requester(request)
        note = (note or "").strip() or None

        request.reject(actor.id, note)
        await self._requests.save(request)
        await self._audit.record(
            event_type=ACCESS_REJECTED,
            actor=actor,
            target=user,
            success=True,
            details=f"requested {request.requested_role.value}; declined"
            + (f": {note}" if note else ""),
            context=context,
        )
        return request

    async def _pending(self, request_id: uuid.UUID) -> AccessRequest:
        request = await self._requests.get(request_id)
        if request is None:
            raise AccessRequestNotFoundError(f"Access request {request_id} not found")
        if not request.is_pending:
            raise AccessRequestDecidedError("This request has already been decided.")
        return request

    async def _requester(self, request: AccessRequest) -> User:
        user = await self._users.get_by_id(request.user_id)
        if user is None:
            raise UserNotFoundError("The requesting account no longer exists.")
        return user

    async def _resolve_roles(self, role_names: list[RoleName]) -> list[Role]:
        roles: list[Role] = []
        for name in dict.fromkeys(role_names):
            role = await self._roles.get_by_name(name)
            if role is None:
                raise UnknownRoleError(f"Role {name.value} does not exist")
            roles.append(role)
        return roles
