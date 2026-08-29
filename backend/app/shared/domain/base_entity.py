"""
ITBIS Shared — Base Domain Entity
All domain entities inherit from this base class.
"""

import uuid
from datetime import datetime, timezone
from typing import Any


class BaseEntity:
    """
    Base class for all domain entities.

    Provides:
    - UUID-based identity
    - Created / updated timestamps
    - Equality based on identity (not attribute values)
    - Domain event collection (to be dispatched after persistence)
    """

    def __init__(self, id: uuid.UUID | None = None) -> None:
        self._id: uuid.UUID = id or uuid.uuid4()
        self._created_at: datetime = datetime.now(timezone.utc)
        self._updated_at: datetime = datetime.now(timezone.utc)
        self._domain_events: list[Any] = []

    @property
    def id(self) -> uuid.UUID:
        return self._id

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def _touch(self) -> None:
        """Update the updated_at timestamp. Call after any state mutation."""
        self._updated_at = datetime.now(timezone.utc)

    def add_domain_event(self, event: Any) -> None:
        """Queue a domain event for dispatch after the entity is persisted."""
        self._domain_events.append(event)

    def collect_domain_events(self) -> list[Any]:
        """Return and clear all pending domain events."""
        events = list(self._domain_events)
        self._domain_events.clear()
        return events

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseEntity):
            return False
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self._id}>"
