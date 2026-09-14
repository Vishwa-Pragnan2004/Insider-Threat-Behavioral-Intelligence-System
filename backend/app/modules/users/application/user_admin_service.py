"""
ITBIS — Users Module: user and role administration

Lets an administrator see who has access to ITBIS and change it: create
accounts with their roles, list users, assign roles, and disable or re-enable
accounts.

Guards against locking the organisation out of its own SOC platform:
  - an administrator can't disable their own account or remove their own
    ADMIN role;
  - the last active administrator can't be disabled or demoted.

Disabling an account also revokes its refresh tokens. Its current access token
stops working at once too, because every permission-guarded endpoint re-checks
that the account is active.

Every change — and every refused attempt — is written to the audit log.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import structlog

from app.modules.identity.application.services.password_service import password_service
from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import RoleName
from app.modules.identity.domain.exceptions import WeakPasswordError
from app.modules.identity.domain.repositories import (
    IRefreshTokenStore,
    IRoleRepository,
    IUserRepository,
)

log = structlog.get_logger(__name__)

USER_CREATED = "USER_CREATED"
ROLES_CHANGED = "USER_ROLES_CHANGED"
ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
ACCOUNT_ENABLED = "ACCOUNT_ENABLED"


class UserAdminError(Exception):
    """Base class for refused user-administration requests."""


class UserNotFoundError(UserAdminError):
    """No user with that ID."""


class UnknownRoleError(UserAdminError):
    """A requested role doesn't exist."""


class DuplicateUserError(UserAdminError):
    """The username or email is already in use."""


class InvalidPasswordError(UserAdminError):
    """The initial password doesn't meet the strength policy."""


class AdminLockoutError(UserAdminError):
    """The change would leave someone, or everyone, without administrator access."""


@dataclass(frozen=True)
class AuditContext:
    ip_address: str | None = None
    user_agent: str | None = None


class UserAdminQueries(Protocol):
    async def list_users(
        self,
        *,
        search: str | None,
        role: RoleName | None,
        is_active: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]: ...

    async def count_active_admins(self) -> int: ...


class AdminAuditLog(Protocol):
    async def record(
        self,
        *,
        event_type: str,
        actor: User,
        target: User,
        success: bool,
        details: str | None = None,
        failure_reason: str | None = None,
        context: AuditContext | None = None,
    ) -> None: ...


def is_admin(user: User) -> bool:
    return user.is_superadmin or user.has_role(RoleName.ADMIN)


def _role_names(roles: list[Role]) -> str:
    return ", ".join(sorted(role.name.value for role in roles)) or "none"


class UserAdminService:
    def __init__(
        self,
        *,
        users: IUserRepository,
        roles: IRoleRepository,
        queries: UserAdminQueries,
        sessions: IRefreshTokenStore,
        audit: AdminAuditLog,
    ) -> None:
        self._users = users
        self._roles = roles
        self._queries = queries
        self._sessions = sessions
        self._audit = audit

    # ─── Reads ──────────────────────────────────────────────

    async def list_users(
        self,
        *,
        search: str | None = None,
        role: RoleName | None = None,
        is_active: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[User], int]:
        return await self._queries.list_users(
            search=search, role=role, is_active=is_active, offset=offset, limit=limit
        )

    async def list_roles(self) -> list[Role]:
        order = {name: index for index, name in enumerate(RoleName)}
        return sorted(await self._roles.get_all(), key=lambda role: order[role.name])

    async def get_user(self, user_id: uuid.UUID) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"User {user_id} not found")
        return user

    # ─── Changes ────────────────────────────────────────────

    async def create_user(
        self,
        actor: User,
        *,
        username: str,
        email: str,
        password: str,
        role_names: list[RoleName],
        full_name: str = "",
        context: AuditContext | None = None,
    ) -> User:
        """
        Create an active account with the given roles.

        Self-registration only ever grants VIEWER; this is how an administrator
        onboards an analyst, SOC engineer or manager directly. Admin-created
        accounts count as verified.
        """
        username, email = username.strip(), email.strip().lower()
        if await self._users.exists_by_email(email):
            raise DuplicateUserError("That email is already registered.")
        if await self._users.exists_by_username(username):
            raise DuplicateUserError("That username is already taken.")
        roles = await self._resolve_roles(role_names)
        try:
            hashed = password_service.hash(password)
        except WeakPasswordError as exc:
            raise InvalidPasswordError(str(exc)) from exc

        user = User(
            id=uuid.uuid4(),
            username=username,
            email=email,
            hashed_password=hashed,
            full_name=full_name.strip(),
            is_active=True,
            is_verified=True,
        )
        user.set_roles(roles)
        saved = await self._users.save(user)
        await self._audit.record(
            event_type=USER_CREATED,
            actor=actor,
            target=saved,
            success=True,
            details=f"account created with roles: {_role_names(saved.roles)}",
            context=context,
        )
        return saved

    async def _resolve_roles(self, role_names: list[RoleName]) -> list[Role]:
        roles: list[Role] = []
        for name in dict.fromkeys(role_names):
            role = await self._roles.get_by_name(name)
            if role is None:
                raise UnknownRoleError(f"Role {name.value} does not exist")
            roles.append(role)
        return roles

    async def set_roles(
        self,
        actor: User,
        user_id: uuid.UUID,
        role_names: list[RoleName],
        *,
        context: AuditContext | None = None,
    ) -> User:
        target = await self.get_user(user_id)
        wanted = list(dict.fromkeys(role_names))
        roles = await self._resolve_roles(wanted)

        # A superadmin keeps administrator access without the ADMIN role.
        if is_admin(target) and not target.is_superadmin and RoleName.ADMIN not in wanted:
            await self._refuse_if_lockout(
                actor,
                target,
                event_type=ROLES_CHANGED,
                self_message="You can't remove your own ADMIN role.",
                context=context,
            )

        before = _role_names(target.roles)
        target.set_roles(roles)
        saved = await self._users.save(target)
        await self._audit.record(
            event_type=ROLES_CHANGED,
            actor=actor,
            target=saved,
            success=True,
            details=f"roles: {before} -> {_role_names(saved.roles)}",
            context=context,
        )
        return saved

    async def disable(
        self, actor: User, user_id: uuid.UUID, *, context: AuditContext | None = None
    ) -> User:
        target = await self.get_user(user_id)
        await self._refuse_if_lockout(
            actor,
            target,
            event_type=ACCOUNT_DISABLED,
            self_message="You can't disable your own account.",
            context=context,
            applies=target.id == actor.id or is_admin(target),
        )
        if not target.is_active:
            return target

        target.disable()
        saved = await self._users.save(target)
        sessions_revoked = await self._revoke_sessions(saved)
        await self._audit.record(
            event_type=ACCOUNT_DISABLED,
            actor=actor,
            target=saved,
            success=True,
            details=(
                "account disabled; refresh tokens revoked"
                if sessions_revoked
                else "account disabled; refresh tokens could NOT be revoked (Redis unavailable)"
            ),
            context=context,
        )
        return saved

    async def enable(
        self, actor: User, user_id: uuid.UUID, *, context: AuditContext | None = None
    ) -> User:
        target = await self.get_user(user_id)
        if target.is_active:
            return target
        target.enable()
        saved = await self._users.save(target)
        await self._audit.record(
            event_type=ACCOUNT_ENABLED,
            actor=actor,
            target=saved,
            success=True,
            details="account re-enabled",
            context=context,
        )
        return saved

    # ─── Guards ─────────────────────────────────────────────

    async def _refuse_if_lockout(
        self,
        actor: User,
        target: User,
        *,
        event_type: str,
        self_message: str,
        context: AuditContext | None,
        applies: bool = True,
    ) -> None:
        if not applies:
            return
        if target.id == actor.id:
            reason = self_message
        elif target.is_active and await self._queries.count_active_admins() <= 1:
            reason = "This is the last active administrator."
        else:
            return
        await self._audit.record(
            event_type=event_type,
            actor=actor,
            target=target,
            success=False,
            failure_reason=reason,
            context=context,
        )
        raise AdminLockoutError(reason)

    async def _revoke_sessions(self, user: User) -> bool:
        try:
            await self._sessions.revoke_all_for_user(str(user.id))
            return True
        except Exception:  # noqa: BLE001 - the account is already locked out
            log.exception("users.session_revocation_failed", user_id=str(user.id))
            return False
