"""
ITBIS — Users Module: access request storage (PostgreSQL)
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.models import AccessRequestModel, UserModel
from app.modules.users.domain.access_request import (
    AccessRequest,
    AccessRequestStatus,
    AccessRequestView,
)

PENDING_LOGIN_MESSAGE = "Your access request is awaiting administrator approval."
REJECTED_LOGIN_MESSAGE = "Your access request was declined. Contact your administrator."


def _to_domain(m: AccessRequestModel) -> AccessRequest:
    return AccessRequest(
        id=m.id,
        user_id=m.user_id,
        requested_role=RoleName(m.requested_role),
        reason=m.reason,
        status=AccessRequestStatus(m.status),
        created_at=m.created_at,
        decided_at=m.decided_at,
        decided_by=m.decided_by,
        decision_note=m.decision_note,
        granted_roles=[RoleName(r) for r in (m.granted_roles or "").split(",") if r],
    )


def _apply(request: AccessRequest, m: AccessRequestModel) -> AccessRequestModel:
    m.id = request.id
    m.user_id = request.user_id
    m.requested_role = request.requested_role.value
    m.reason = request.reason
    m.status = request.status.value
    m.created_at = request.created_at
    m.decided_at = request.decided_at
    m.decided_by = request.decided_by
    m.decision_note = request.decision_note
    m.granted_roles = ",".join(role.value for role in request.granted_roles) or None
    return m


class SQLAccessRequestStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, request: AccessRequest) -> None:
        # The requesting user is only pending in the session so far; flush it
        # first so the foreign key has a row to point at.
        await self._session.flush()
        self._session.add(_apply(request, AccessRequestModel()))
        await self._session.flush()

    async def get(self, request_id: uuid.UUID) -> AccessRequest | None:
        model = await self._session.get(AccessRequestModel, request_id)
        return _to_domain(model) if model else None

    async def save(self, request: AccessRequest) -> None:
        model = await self._session.get(AccessRequestModel, request.id)
        if model is None:
            await self.add(request)
            return
        _apply(request, model)
        await self._session.flush()

    async def list_views(
        self, status: AccessRequestStatus | None = None
    ) -> list[AccessRequestView]:
        return await self._views(status=status)

    async def get_view(self, request_id: uuid.UUID) -> AccessRequestView | None:
        views = await self._views(request_id=request_id)
        return views[0] if views else None

    async def count(self, status: AccessRequestStatus) -> int:
        stmt = (
            select(func.count())
            .select_from(AccessRequestModel)
            .where(AccessRequestModel.status == status.value)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def _views(
        self,
        *,
        status: AccessRequestStatus | None = None,
        request_id: uuid.UUID | None = None,
    ) -> list[AccessRequestView]:
        decider = aliased(UserModel)
        stmt = (
            select(
                AccessRequestModel,
                UserModel.username,
                UserModel.email,
                UserModel.full_name,
                decider.username,
            )
            .join(UserModel, UserModel.id == AccessRequestModel.user_id)
            .outerjoin(decider, decider.id == AccessRequestModel.decided_by)
            .order_by(AccessRequestModel.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(AccessRequestModel.status == status.value)
        if request_id is not None:
            stmt = stmt.where(AccessRequestModel.id == request_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            AccessRequestView(
                request=_to_domain(model),
                username=username,
                email=email,
                full_name=full_name or "",
                decided_by_username=decided_by,
            )
            for model, username, email, full_name, decided_by in rows
        ]


async def login_refusal_message(session: AsyncSession, identifier: str) -> str | None:
    """
    Why a disabled account can't sign in, if it's because of an access request.

    Only called once the password has been verified, so it tells nothing to
    someone who doesn't know it.
    """
    stmt = (
        select(AccessRequestModel.status)
        .join(UserModel, UserModel.id == AccessRequestModel.user_id)
        .where(
            or_(
                func.lower(UserModel.email) == identifier.strip().lower(),
                func.lower(UserModel.username) == identifier.strip().lower(),
            )
        )
        .order_by(AccessRequestModel.created_at.desc())
        .limit(1)
    )
    status = (await session.execute(stmt)).scalar_one_or_none()
    if status == AccessRequestStatus.PENDING.value:
        return PENDING_LOGIN_MESSAGE
    if status == AccessRequestStatus.REJECTED.value:
        return REJECTED_LOGIN_MESSAGE
    return None
