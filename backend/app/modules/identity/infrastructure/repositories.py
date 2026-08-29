"""
ITBIS — Identity Module: Concrete Repositories
Implements domain repository interfaces using SQLAlchemy.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.entities import Permission, Role, User
from app.modules.identity.domain.enums import RoleName
from app.modules.identity.domain.repositories import IRoleRepository, IUserRepository
from app.modules.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    UserModel,
)


class SQLUserRepository(IUserRepository):
    """SQLAlchemy implementation of IUserRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_domain(self, model: UserModel) -> User:
        """Convert SQLAlchemy model to pure domain entity."""
        roles = []
        for role_model in model.roles:
            permissions = [
                Permission(id=p.id, name=p.name) for p in role_model.permissions
            ]
            roles.append(
                Role(id=role_model.id, name=role_model.name, permissions=permissions)
            )

        return User(
            id=model.id,
            username=model.username,
            email=model.email,
            hashed_password=model.hashed_password,
            full_name=model.full_name,
            is_active=model.is_active,
            is_verified=model.is_verified,
            is_superadmin=model.is_superadmin,
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_login_at=model.last_login_at,
            roles=roles,
        )

    def _to_model(self, entity: User, existing_model: Optional[UserModel] = None) -> UserModel:
        """Convert domain entity to SQLAlchemy model."""
        model = existing_model or UserModel(id=entity.id)
        model.username = entity.username
        model.email = entity.email
        model.hashed_password = entity.hashed_password
        model.full_name = entity.full_name
        model.is_active = entity.is_active
        model.is_verified = entity.is_verified
        model.is_superadmin = entity.is_superadmin
        model.created_at = entity.created_at
        model.updated_at = entity.updated_at
        model.last_login_at = entity.last_login_at
        return model

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.email == email.strip().lower())
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def get_by_username(self, username: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.username == username.strip().lower())
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def save(self, user: User) -> User:
        # Check if exists
        stmt = select(UserModel).where(UserModel.id == user.id)
        result = await self.session.execute(stmt)
        existing = result.scalars().first()

        model = self._to_model(user, existing)
        
        # Handle role assignments
        if user.roles:
            role_ids = [r.id for r in user.roles]
            role_stmt = select(RoleModel).where(RoleModel.id.in_(role_ids))
            role_result = await self.session.execute(role_stmt)
            model.roles = list(role_result.scalars().all())
        else:
            model.roles = []

        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def exists_by_email(self, email: str) -> bool:
        stmt = select(UserModel.id).where(UserModel.email == email.strip().lower())
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def exists_by_username(self, username: str) -> bool:
        stmt = select(UserModel.id).where(UserModel.username == username.strip().lower())
        result = await self.session.execute(stmt)
        return result.first() is not None

    async def assign_role(self, user_id: uuid.UUID, role_name: RoleName) -> None:
        user_stmt = select(UserModel).where(UserModel.id == user_id)
        user_result = await self.session.execute(user_stmt)
        user_model = user_result.scalars().first()
        if not user_model:
            return

        role_stmt = select(RoleModel).where(RoleModel.name == role_name)
        role_result = await self.session.execute(role_stmt)
        role_model = role_result.scalars().first()
        
        if role_model and role_model not in user_model.roles:
            user_model.roles.append(role_model)
            await self.session.flush()


class SQLRoleRepository(IRoleRepository):
    """SQLAlchemy implementation of IRoleRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_domain(self, model: RoleModel) -> Role:
        permissions = [Permission(id=p.id, name=p.name) for p in model.permissions]
        return Role(id=model.id, name=model.name, permissions=permissions)

    async def get_by_name(self, name: RoleName) -> Optional[Role]:
        stmt = select(RoleModel).where(RoleModel.name == name)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        return self._to_domain(model) if model else None

    async def get_all(self) -> list[Role]:
        stmt = select(RoleModel)
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        return [self._to_domain(m) for m in models]

    async def save(self, role: Role) -> Role:
        stmt = select(RoleModel).where(RoleModel.id == role.id)
        result = await self.session.execute(stmt)
        existing = result.scalars().first()

        model = existing or RoleModel(id=role.id, name=role.name)
        
        if role.permissions:
            perm_ids = [p.id for p in role.permissions]
            perm_stmt = select(PermissionModel).where(PermissionModel.id.in_(perm_ids))
            perm_result = await self.session.execute(perm_stmt)
            model.permissions = list(perm_result.scalars().all())
        else:
            model.permissions = []

        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)
