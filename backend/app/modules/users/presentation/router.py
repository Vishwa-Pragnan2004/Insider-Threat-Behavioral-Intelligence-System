"""
ITBIS — Users Module: user and role administration API

    POST /api/v1/users                   create an account with roles
    GET  /api/v1/users                   list users (search, role, active filters)
    GET  /api/v1/users/roles             roles and the permissions each grants
    GET  /api/v1/users/{user_id}         one user
    PUT  /api/v1/users/{user_id}/roles   replace a user's roles
    POST /api/v1/users/{user_id}/disable disable an account (revokes its sessions)
    POST /api/v1/users/{user_id}/enable  re-enable an account

Reads need users:read; creating needs users:create and changes need
users:update (both ADMIN only).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import PermissionName, RoleName
from app.modules.identity.infrastructure.redis_token_store import RedisTokenStore
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)
from app.modules.users.application.user_admin_service import (
    AdminLockoutError,
    AuditContext,
    DuplicateUserError,
    InvalidPasswordError,
    UnknownRoleError,
    UserAdminError,
    UserAdminService,
    UserNotFoundError,
)
from app.modules.users.infrastructure.sql_user_admin import (
    SQLAdminAuditLog,
    SQLUserAdminQueries,
)

router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────


class UserOut(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]
    is_active: bool
    is_superadmin: bool
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_user(cls, user: User) -> UserOut:
        return cls(
            id=str(user.id),
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            roles=sorted(role.name.value for role in user.roles),
            permissions=sorted(user.permission_names()),
            is_active=user.is_active,
            is_superadmin=user.is_superadmin,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class UserListOut(BaseModel):
    users: list[UserOut]
    total: int
    offset: int
    limit: int


class RoleOut(BaseModel):
    name: str
    permissions: list[str]

    @classmethod
    def from_role(cls, role: Role) -> RoleOut:
        return cls(
            name=role.name.value,
            permissions=sorted(permission.name.value for permission in role.permissions),
        )


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    email: EmailStr
    full_name: str = Field("", max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    roles: list[RoleName] = Field(..., min_length=1)


class SetRolesRequest(BaseModel):
    roles: list[RoleName] = Field(..., min_length=1)


# ─── Wiring ─────────────────────────────────────────────────


def _service(session: AsyncSession, redis: Any) -> UserAdminService:
    return UserAdminService(
        users=SQLUserRepository(session),
        roles=SQLRoleRepository(session),
        queries=SQLUserAdminQueries(session),
        sessions=RedisTokenStore(redis),
        audit=SQLAdminAuditLog(session),
    )


def _context(request: Request) -> AuditContext:
    return AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


async def _refused(session: AsyncSession, exc: UserAdminError) -> HTTPException:
    # Commit first: the refusal's audit row would otherwise be rolled back with
    # the failed request.
    await session.commit()
    if isinstance(exc, UserNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AdminLockoutError | DuplicateUserError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, UnknownRoleError | InvalidPasswordError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc))


# ─── Reads ──────────────────────────────────────────────────


@router.get(
    "",
    response_model=UserListOut,
    summary="List users",
    dependencies=[Depends(require_permission(PermissionName.USERS_READ))],
)
async def list_users(
    search: str | None = Query(None, max_length=100),
    role: RoleName | None = None,
    is_active: bool | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> UserListOut:
    users, total = await _service(session, redis).list_users(
        search=search, role=role, is_active=is_active, offset=offset, limit=limit
    )
    return UserListOut(
        users=[UserOut.from_user(u) for u in users], total=total, offset=offset, limit=limit
    )


@router.get(
    "/roles",
    response_model=list[RoleOut],
    summary="List roles and the permissions each grants",
    dependencies=[Depends(require_permission(PermissionName.USERS_READ))],
)
async def list_roles(
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> list[RoleOut]:
    return [RoleOut.from_role(role) for role in await _service(session, redis).list_roles()]


@router.get(
    "/{user_id}",
    response_model=UserOut,
    summary="Get one user",
    dependencies=[Depends(require_permission(PermissionName.USERS_READ))],
)
async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> UserOut:
    try:
        return UserOut.from_user(await _service(session, redis).get_user(user_id))
    except UserAdminError as exc:
        raise await _refused(session, exc) from exc


# ─── Changes ────────────────────────────────────────────────


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account with roles",
    dependencies=[Depends(require_permission(PermissionName.USERS_CREATE))],
)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    actor: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> UserOut:
    try:
        user = await _service(session, redis).create_user(
            actor,
            username=payload.username,
            email=str(payload.email),
            password=payload.password,
            role_names=payload.roles,
            full_name=payload.full_name,
            context=_context(request),
        )
    except UserAdminError as exc:
        raise await _refused(session, exc) from exc
    return UserOut.from_user(user)


@router.put(
    "/{user_id}/roles",
    response_model=UserOut,
    summary="Replace a user's roles",
    dependencies=[Depends(require_permission(PermissionName.USERS_UPDATE))],
)
async def set_user_roles(
    user_id: uuid.UUID,
    payload: SetRolesRequest,
    request: Request,
    actor: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> UserOut:
    try:
        user = await _service(session, redis).set_roles(
            actor, user_id, payload.roles, context=_context(request)
        )
    except UserAdminError as exc:
        raise await _refused(session, exc) from exc
    return UserOut.from_user(user)


@router.post(
    "/{user_id}/disable",
    response_model=UserOut,
    summary="Disable an account and revoke its sessions",
    dependencies=[Depends(require_permission(PermissionName.USERS_UPDATE))],
)
async def disable_user(
    user_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> UserOut:
    try:
        user = await _service(session, redis).disable(actor, user_id, context=_context(request))
    except UserAdminError as exc:
        raise await _refused(session, exc) from exc
    return UserOut.from_user(user)


@router.post(
    "/{user_id}/enable",
    response_model=UserOut,
    summary="Re-enable an account",
    dependencies=[Depends(require_permission(PermissionName.USERS_UPDATE))],
)
async def enable_user(
    user_id: uuid.UUID,
    request: Request,
    actor: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
    redis: Any = Depends(get_redis),
) -> UserOut:
    try:
        user = await _service(session, redis).enable(actor, user_id, context=_context(request))
    except UserAdminError as exc:
        raise await _refused(session, exc) from exc
    return UserOut.from_user(user)
