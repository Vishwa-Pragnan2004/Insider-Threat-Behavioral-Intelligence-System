"""
ITBIS — Users Module: access request API

    POST /api/v1/auth/access-requests                     ask for an account (public)
    GET  /api/v1/users/access-requests                    the request queue (users:read)
    POST /api/v1/users/access-requests/{id}/approve       grant roles, enable (users:update)
    POST /api/v1/users/access-requests/{id}/reject        decline (users:update)

`admin_router` must be mounted before the users router, whose `/{user_id}`
route would otherwise capture `/access-requests`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName, RoleName
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)
from app.modules.users.application.access_request_service import (
    AccessRequestDecidedError,
    AccessRequestNotFoundError,
    AccessRequestService,
    RoleNotRequestableError,
)
from app.modules.users.application.user_admin_service import (
    AuditContext,
    DuplicateUserError,
    InvalidPasswordError,
    UnknownRoleError,
    UserAdminError,
    UserNotFoundError,
)
from app.modules.users.domain.access_request import AccessRequestStatus, AccessRequestView
from app.modules.users.infrastructure.sql_access_requests import SQLAccessRequestStore
from app.modules.users.infrastructure.sql_user_admin import SQLAdminAuditLog

public_router = APIRouter()
admin_router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────


class AccessRequestCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    requested_role: RoleName
    reason: str = Field(..., min_length=10, max_length=1000)


class AccessRequestAccepted(BaseModel):
    id: str
    status: str
    message: str


class AccessRequestOut(BaseModel):
    id: str
    user_id: str
    username: str
    email: str
    full_name: str
    requested_role: str
    reason: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    decided_by: str | None
    decision_note: str | None
    granted_roles: list[str]

    @classmethod
    def from_view(cls, view: AccessRequestView) -> AccessRequestOut:
        r = view.request
        return cls(
            id=str(r.id),
            user_id=str(r.user_id),
            username=view.username,
            email=view.email,
            full_name=view.full_name,
            requested_role=r.requested_role.value,
            reason=r.reason,
            status=r.status.value,
            created_at=r.created_at,
            decided_at=r.decided_at,
            decided_by=view.decided_by_username,
            decision_note=r.decision_note,
            granted_roles=[role.value for role in r.granted_roles],
        )


class AccessRequestListOut(BaseModel):
    requests: list[AccessRequestOut]
    total: int
    pending: int


class ApproveRequest(BaseModel):
    roles: list[RoleName] = Field(..., min_length=1)


class RejectRequest(BaseModel):
    note: str | None = Field(None, max_length=500)


# ─── Wiring ─────────────────────────────────────────────────


def _service(session: AsyncSession) -> tuple[AccessRequestService, SQLAccessRequestStore]:
    store = SQLAccessRequestStore(session)
    service = AccessRequestService(
        users=SQLUserRepository(session),
        roles=SQLRoleRepository(session),
        requests=store,
        audit=SQLAdminAuditLog(session),
    )
    return service, store


def _context(request: Request) -> AuditContext:
    return AuditContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _http_error(exc: UserAdminError) -> HTTPException:
    if isinstance(exc, AccessRequestNotFoundError | UserNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, AccessRequestDecidedError | DuplicateUserError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, InvalidPasswordError | RoleNotRequestableError | UnknownRoleError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc))


async def _decided(store: SQLAccessRequestStore, request_id: uuid.UUID) -> AccessRequestOut:
    view = await store.get_view(request_id)
    assert view is not None  # it was just decided in this session
    return AccessRequestOut.from_view(view)


# ─── Public ─────────────────────────────────────────────────


@public_router.post(
    "/access-requests",
    response_model=AccessRequestAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request an account and a role (needs administrator approval)",
)
async def submit_access_request(
    payload: AccessRequestCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AccessRequestAccepted:
    service, _ = _service(session)
    try:
        created = await service.submit(
            username=payload.username,
            email=str(payload.email),
            full_name=payload.full_name,
            password=payload.password,
            requested_role=payload.requested_role,
            reason=payload.reason,
            context=_context(request),
        )
    except UserAdminError as exc:
        raise _http_error(exc) from exc
    return AccessRequestAccepted(
        id=str(created.id),
        status=created.status.value,
        message=(
            "Request submitted. An administrator will review it; you can sign in "
            "once it's approved."
        ),
    )


# ─── Administration ─────────────────────────────────────────


@admin_router.get(
    "/access-requests",
    response_model=AccessRequestListOut,
    summary="List access requests",
    dependencies=[Depends(require_permission(PermissionName.USERS_READ))],
)
async def list_access_requests(
    # Exposed as ?status=; the Python name avoids shadowing fastapi.status.
    status_filter: AccessRequestStatus | None = Query(None, alias="status"),
    session: AsyncSession = Depends(get_db),
) -> AccessRequestListOut:
    views, pending = await _service(session)[0].list_requests(status_filter)
    return AccessRequestListOut(
        requests=[AccessRequestOut.from_view(v) for v in views],
        total=len(views),
        pending=pending,
    )


@admin_router.post(
    "/access-requests/{request_id}/approve",
    response_model=AccessRequestOut,
    summary="Approve an access request, granting roles",
    dependencies=[Depends(require_permission(PermissionName.USERS_UPDATE))],
)
async def approve_access_request(
    request_id: uuid.UUID,
    payload: ApproveRequest,
    request: Request,
    actor: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    service, store = _service(session)
    try:
        await service.approve(actor, request_id, payload.roles, context=_context(request))
    except UserAdminError as exc:
        raise _http_error(exc) from exc
    return await _decided(store, request_id)


@admin_router.post(
    "/access-requests/{request_id}/reject",
    response_model=AccessRequestOut,
    summary="Reject an access request",
    dependencies=[Depends(require_permission(PermissionName.USERS_UPDATE))],
)
async def reject_access_request(
    request_id: uuid.UUID,
    payload: RejectRequest,
    request: Request,
    actor: User = Depends(require_active_user),
    session: AsyncSession = Depends(get_db),
) -> AccessRequestOut:
    service, store = _service(session)
    try:
        await service.reject(actor, request_id, payload.note, context=_context(request))
    except UserAdminError as exc:
        raise _http_error(exc) from exc
    return await _decided(store, request_id)
