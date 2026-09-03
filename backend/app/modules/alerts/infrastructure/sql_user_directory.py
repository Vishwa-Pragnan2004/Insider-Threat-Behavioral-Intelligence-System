"""
ITBIS — Alerts Module: SQL-backed implementation of IUserDirectory.

A thin adapter that wraps the existing `SQLUserRepository` from the
identity module.  The adapter is intentionally minimal: only the
single `user_exists` method is required, and the rest of the user
repository is out of scope.

This is the *only* place in the alerts module that imports
`app.modules.identity.*`; the application layer is kept free of
SQLAlchemy.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.alerts.domain.repositories import IUserDirectory
from app.modules.identity.infrastructure.models import UserModel


class SqlUserDirectory(IUserDirectory):
    """SQLAlchemy implementation of IUserDirectory."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def user_exists(self, user_id: str) -> bool:
        # The `assigned_to` field is a free-form string (the auth
        # service can issue user ids as either UUIDs or short
        # identifiers); we match either the canonical UUID column
        # (if `user_id` parses as a UUID) or the textual id column
        # (any other value).  Both columns are indexed on UserModel.
        from uuid import UUID

        stmt = select(UserModel.id)
        try:
            uuid_obj = UUID(user_id)
        except (TypeError, ValueError):
            return False
        result = await self.session.execute(stmt.where(UserModel.id == uuid_obj))
        return result.scalar_one_or_none() is not None
