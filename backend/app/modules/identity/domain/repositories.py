"""
ITBIS — Identity Module: Repository Interfaces
Abstract contracts for user and role persistence.
Concrete implementations live in infrastructure/.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Optional

from app.modules.identity.domain.entities import Role, User
from app.modules.identity.domain.enums import RoleName


class IUserRepository(ABC):
    """Abstract contract for user persistence."""

    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """Find a user by their UUID. Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """Find a user by email (case-insensitive). Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]:
        """Find a user by username (case-insensitive). Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    async def save(self, user: User) -> User:
        """Persist a new user or update an existing one."""
        raise NotImplementedError

    @abstractmethod
    async def exists_by_email(self, email: str) -> bool:
        """Return True if any user has this email address."""
        raise NotImplementedError

    @abstractmethod
    async def exists_by_username(self, username: str) -> bool:
        """Return True if any user has this username."""
        raise NotImplementedError

    @abstractmethod
    async def assign_role(self, user_id: uuid.UUID, role_name: RoleName) -> None:
        """Assign the named role to a user."""
        raise NotImplementedError


class IRoleRepository(ABC):
    """Abstract contract for role and permission persistence."""

    @abstractmethod
    async def get_by_name(self, name: RoleName) -> Optional[Role]:
        """Find a role by its name. Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    async def get_all(self) -> list[Role]:
        """Return all roles with their associated permissions."""
        raise NotImplementedError

    @abstractmethod
    async def save(self, role: Role) -> Role:
        """Persist a role."""
        raise NotImplementedError


class IRefreshTokenStore(ABC):
    """Abstract contract for refresh token storage and revocation."""

    @abstractmethod
    async def store(self, jti: str, user_id: str, ttl_seconds: int) -> None:
        """Store a refresh token JTI with its owner and TTL."""
        raise NotImplementedError

    @abstractmethod
    async def is_valid(self, jti: str) -> bool:
        """Return True if the token JTI exists and has not been revoked."""
        raise NotImplementedError

    @abstractmethod
    async def revoke(self, jti: str) -> None:
        """Revoke a refresh token by deleting it from the store."""
        raise NotImplementedError

    @abstractmethod
    async def revoke_all_for_user(self, user_id: str) -> None:
        """Revoke all refresh tokens belonging to a user (e.g., on password change)."""
        raise NotImplementedError
