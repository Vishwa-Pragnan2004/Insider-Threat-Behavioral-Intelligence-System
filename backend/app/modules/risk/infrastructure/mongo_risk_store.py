"""
ITBIS — Risk Module: MongoDB store for daily employee risk scores
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.anomaly.domain.enums import RiskLevel
from app.modules.risk.domain.model import EmployeeRiskScore, RiskComponent


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class MongoRiskScoreStore:
    COLLECTION = "employee_risk_scores"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._indexes_built = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_built:
            return
        coll = self.db[self.COLLECTION]
        await coll.create_index("key", unique=True, name="ux_risk_key")
        await coll.create_index([("user_id", 1), ("day", -1)], name="ix_risk_user_day")
        await coll.create_index([("day", -1), ("priority", -1)], name="ix_risk_day_priority")
        self._indexes_built = True

    @staticmethod
    def _to_doc(r: EmployeeRiskScore) -> dict:
        return {
            "_id": str(r.id),
            "key": r.key,
            "user_id": r.user_id,
            "day": r.day,
            "score": r.score,
            "level": r.level.value,
            "components": {c.value: v for c, v in r.components.items()},
            "top_signals": r.top_signals,
            "dominant_component": r.dominant_component.value if r.dominant_component else None,
            "trend": r.trend,
            "priority": r.priority,
            "model_version": r.model_version,
            "computed_at": r.computed_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> EmployeeRiskScore:
        dominant = doc.get("dominant_component")
        return EmployeeRiskScore(
            user_id=doc["user_id"],
            day=_as_utc(doc["day"]),
            score=float(doc.get("score") or 0.0),
            level=RiskLevel(doc.get("level", "LOW")),
            components={
                RiskComponent(k): float(v) for k, v in (doc.get("components") or {}).items()
            },
            top_signals=list(doc.get("top_signals") or []),
            dominant_component=RiskComponent(dominant) if dominant else None,
            trend=doc.get("trend"),
            priority=float(doc.get("priority") or 0.0),
            model_version=doc.get("model_version", "unknown"),
            computed_at=_as_utc(doc.get("computed_at")) or datetime.now(UTC),
        )

    async def upsert_many(self, scores: list[EmployeeRiskScore]) -> None:
        if not scores:
            return
        await self._ensure_indexes()
        coll = self.db[self.COLLECTION]
        for score in scores:
            doc = self._to_doc(score)
            doc_id = doc.pop("_id")
            await coll.update_one(
                {"key": score.key}, {"$set": doc, "$setOnInsert": {"_id": doc_id}}, upsert=True
            )

    async def previous_scores(self, user_id: str, before: datetime, days: int = 7) -> list[float]:
        """Scores for the `days` days before `before`, oldest first."""
        cursor = (
            self.db[self.COLLECTION]
            .find(
                {"user_id": user_id, "day": {"$gte": before - timedelta(days=days), "$lt": before}}
            )
            .sort("day", 1)
        )
        return [float(d.get("score") or 0.0) async for d in cursor]

    async def series(self, user_id: str, start: datetime, end: datetime) -> list[EmployeeRiskScore]:
        cursor = (
            self.db[self.COLLECTION]
            .find({"user_id": user_id, "day": {"$gte": start, "$lt": end}})
            .sort("day", 1)
        )
        return [self._from_doc(d) async for d in cursor]

    async def latest_per_user(
        self, *, since: datetime, limit: int = 50, min_priority: float | None = None
    ) -> list[EmployeeRiskScore]:
        """Each person's most recent score since `since`, highest priority first."""
        latest: dict[str, dict] = {}
        cursor = self.db[self.COLLECTION].find({"day": {"$gte": since}}).sort("day", -1)
        async for doc in cursor:
            latest.setdefault(doc["user_id"], doc)
        ranked = sorted(
            latest.values(), key=lambda d: (-(d.get("priority") or 0.0), -(d.get("score") or 0.0))
        )
        if min_priority is not None:
            ranked = [d for d in ranked if (d.get("priority") or 0.0) >= min_priority]
        return [self._from_doc(d) for d in ranked[:limit]]
