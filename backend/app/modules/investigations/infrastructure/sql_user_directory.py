"""
ITBIS — Investigations Module: SQL-backed implementation of IUserDirectory.

A thin adapter that wraps the existing `SQLUserRepository` from the
identity module.  This is the *only* place in the investigations
module that imports `app.modules.identity.*`; the application layer
is kept free of SQLAlchemy.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.investigations.domain.repositories import IUserDirectory
from app.modules.identity.infrastructure.models import UserModel


class SqlUserDirectory(IUserDirectory):
    """SQLAlchemy implementation of IUserDirectory."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def user_exists(self, user_id: str) -> bool:
        stmt = select(UserModel.id)
        try:
            uuid_obj = UUID(user_id)
        except (TypeError, ValueError):
            return False
        result = await self.session.execute(stmt.where(UserModel.id == uuid_obj))
        return result.scalar_one_or_none() is not None
