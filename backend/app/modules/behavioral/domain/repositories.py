"""
ITBIS — Behavioral Module: Repository Interfaces
"""
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from app.modules.behavioral.domain.entities import BehavioralBaseline, BehavioralFeatures


class IBehavioralFeatureStore(ABC):
    """Persistence for computed behavioral features (MongoDB)."""

    @abstractmethod
    async def upsert_many(self, features: Sequence[BehavioralFeatures]) -> int:
        """Upsert a batch of feature rows. Returns count upserted."""

    @abstractmethod
    async def list_for_user(
        self,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        source_dataset: str | None = None,
    ) -> list[BehavioralFeatures]:
        """List feature rows for a user, optionally filtered by date range."""

    @abstractmethod
    async def list_users_with_features(
        self, source_dataset: str | None = None
    ) -> list[str]:
        """Return the set of distinct user_ids that have features stored."""

    @abstractmethod
    async def list_in_window(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        source_dataset: str | None = None,
    ) -> list[BehavioralFeatures]:
        """List ALL feature rows in the [start, end) window (Phase 5 export)."""

    @abstractmethod
    async def list_all_features(
        self,
        source_dataset: str | None = None,
        window: str | None = None,
    ) -> list[BehavioralFeatures]:
        """List all feature rows for ML training (no date filtering)."""


class IBehavioralBaselineRepository(ABC):
    """Persistence for per-user behavioral baselines (Postgres)."""

    @abstractmethod
    async def save(self, baseline: BehavioralBaseline) -> BehavioralBaseline:
        """Insert or update a baseline for (user_id, feature_version)."""

    @abstractmethod
    async def get(
        self, user_id: str, feature_version: str
    ) -> BehavioralBaseline | None:
        """Return the baseline for a user, or None if absent."""

    @abstractmethod
    async def list_all(self) -> Sequence[BehavioralBaseline]:
        """Return all baselines (small cardinality — used by admin tools)."""


class IBehavioralEventSource(ABC):
    """
    Read-only access to canonical events for feature engineering.

    Implemented by the activity module's Mongo store.  Defined here to keep
    the behavioral module's interface independent from activity's domain
    types.
    """

    @abstractmethod
    async def find_events(
        self,
        *,
        user_id: str | None = None,
        source_dataset: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100_000,
    ) -> list[dict]:
        """Return canonical event documents matching the filters."""
