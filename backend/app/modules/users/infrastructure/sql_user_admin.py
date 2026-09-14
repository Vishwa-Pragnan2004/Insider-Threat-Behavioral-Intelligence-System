"""
ITBIS — Users Module: SQL-backed queries and audit writer for user administration.
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.models import AuthAuditLogModel, RoleModel, UserModel
from app.modules.identity.infrastructure.repositories import SQLUserRepository
from app.modules.users.application.user_admin_service import AuditContext

log = structlog.get_logger(__name__)


class SQLUserAdminQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._mapper = SQLUserRepository(session)

    async def list_users(
        self,
        *,
        search: str | None,
        role: RoleName | None,
        is_active: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[User], int]:
        stmt = select(UserModel)
        if search and search.strip():
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    UserModel.username.ilike(pattern),
                    UserModel.email.ilike(pattern),
                    UserModel.full_name.ilike(pattern),
                )
            )
        if role is not None:
            stmt = stmt.where(UserModel.roles.any(RoleModel.name == role))
        if is_active is not None:
            stmt = stmt.where(UserModel.is_active.is_(is_active))

        total = await self._session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self._session.execute(
            stmt.order_by(UserModel.created_at.desc()).offset(offset).limit(limit)
        )
        users = [self._mapper._to_domain(model) for model in rows.scalars().all()]
        return users, int(total or 0)

    async def count_active_admins(self) -> int:
        stmt = (
            select(func.count())
            .select_from(UserModel)
            .where(
                UserModel.is_active.is_(True),
                or_(
                    UserModel.is_superadmin.is_(True),
                    UserModel.roles.any(RoleModel.name == RoleName.ADMIN),
                ),
            )
        )
        return int(await self._session.scalar(stmt) or 0)


class SQLAdminAuditLog:
    """Writes administrative actions to auth_audit_log, plus a structured log line."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
    ) -> None:
        context = context or AuditContext()
        self._session.add(
            AuthAuditLogModel(
                event_type=event_type,
                occurred_at=datetime.now(UTC),
                user_id=target.id,
                username=target.username,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                success=success,
                failure_reason=failure_reason[:255] if failure_reason else None,
                actor_user_id=actor.id,
                details=details,
            )
        )
        await self._session.flush()
        log.info(
            "admin_audit_event",
            event_type=event_type,
            actor=actor.username,
            target=target.username,
            success=success,
            details=details,
            failure_reason=failure_reason,
        )
