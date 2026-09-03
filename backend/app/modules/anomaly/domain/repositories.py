"""
ITBIS — Anomaly Module: Repository Interfaces
"""
import uuid
from abc import ABC, abstractmethod
from datetime import datetime

from app.modules.anomaly.domain.entities import AnomalyResult
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel


class IAnomalyResultStore(ABC):
    """Persistence for AnomalyResult (MongoDB)."""

    @abstractmethod
    async def upsert(self, result: AnomalyResult) -> None:
        """Insert or replace one result keyed by (user_id, window, window_start)."""

    @abstractmethod
    async def list_for_user(
        self,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        risk_level: RiskLevel | None = None,
        limit: int = 100,
    ) -> list[AnomalyResult]:
        """List results for a user, optionally filtered by date range / risk level."""

    @abstractmethod
    async def list_recent(
        self,
        risk_level: RiskLevel | None = None,
        prediction: AnomalyPrediction | None = None,
        limit: int = 100,
    ) -> list[AnomalyResult]:
        """List recent results across all users, optionally filtered."""

    @abstractmethod
    async def get_by_id(self, result_id: uuid.UUID) -> AnomalyResult | None:
        """Return a single result by its UUID, or None if not found."""
