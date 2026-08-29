"""
ITBIS Shared — Base Repository Interface
All module repositories implement this interface.
Enforces the Repository Pattern across the codebase.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar

from app.shared.domain.base_entity import BaseEntity

T = TypeVar("T", bound=BaseEntity)


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository.

    All concrete repositories in every module must implement this interface.
    Provides a consistent data-access contract independent of the storage backend.
    """

    @abstractmethod
    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        """Retrieve a single entity by its UUID. Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Persist a new entity or update an existing one."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, entity_id: uuid.UUID) -> bool:
        """Delete an entity by ID. Returns True if deleted, False if not found."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Return a paginated list of all entities."""
        raise NotImplementedError
