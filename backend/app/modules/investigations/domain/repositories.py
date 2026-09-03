"""
ITBIS — Investigations Module: Repository Interfaces
"""
import uuid
from abc import ABC, abstractmethod

from app.modules.investigations.domain.entities import Investigation, InvestigationNote
from app.modules.investigations.domain.enums import InvestigationStatus


class IUserDirectory(ABC):
    """
    Read-only port for validating that a user exists.

    The investigations module only needs to ask "does this user
    exist?" before persisting an `assigned_to` reference.  We define
    a module-local port (consistent with the existing
    `IInvestigationRepository` pattern) and inject a concrete
    implementation via FastAPI dependencies.  This keeps the
    investigations application layer free of SQLAlchemy details.
    """

    @abstractmethod
    async def user_exists(self, user_id: str) -> bool:
        """Return True if a user with the given id exists."""
        raise NotImplementedError


class IInvestigationRepository(ABC):
    """Persistence for Investigation (MongoDB)."""

    @abstractmethod
    async def upsert(self, investigation: Investigation) -> Investigation:
        """Insert or update by id."""

    @abstractmethod
    async def get_by_id(self, investigation_id: uuid.UUID) -> Investigation | None:
        ...

    @abstractmethod
    async def list_investigations(
        self,
        *,
        status: InvestigationStatus | None = None,
        assigned_to: str | None = None,
        severity: str | None = None,
        related_user_id: str | None = None,
        created_by: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Investigation]:
        ...

    @abstractmethod
    async def count_investigations(
        self,
        *,
        status: InvestigationStatus | None = None,
        assigned_to: str | None = None,
        severity: str | None = None,
        related_user_id: str | None = None,
        created_by: str | None = None,
    ) -> int:
        ...


class IInvestigationNoteRepository(ABC):
    """Persistence for immutable InvestigationNote (MongoDB)."""

    @abstractmethod
    async def append(self, note: InvestigationNote) -> None:
        """Append a note.  Notes are append-only — no update or delete."""

    @abstractmethod
    async def list_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> list[InvestigationNote]:
        """Return all notes for the investigation, oldest first."""
