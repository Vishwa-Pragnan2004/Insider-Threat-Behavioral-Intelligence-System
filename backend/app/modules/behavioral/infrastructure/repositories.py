"""
ITBIS — Behavioral Module: Concrete Repositories
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.behavioral.domain.entities import BehavioralBaseline, BehavioralFeatures
from app.modules.behavioral.domain.enums import FEATURE_VERSION
from app.modules.behavioral.domain.repositories import (
    IBehavioralBaselineRepository,
    IBehavioralFeatureStore,
)
from app.modules.behavioral.infrastructure.models import BehavioralBaselineModel

# ─── Mongo feature store ────────────────────────────────────


class MongoBehavioralFeatureStore(IBehavioralFeatureStore):
    """Persists BehavioralFeatures documents to MongoDB."""

    COLLECTION = "behavioral_features"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    @staticmethod
    def _to_doc(f: BehavioralFeatures) -> dict:
        return {
            "_id": str(f.id),
            "user_id": f.user_id,
            "window": f.window,
            "window_start": f.window_start,
            "window_end": f.window_end,
            "source_dataset": f.source_dataset,
            "features": dict(f.features),
            "feature_version": f.feature_version,
            "event_count": int(f.event_count),
            "generated_at": f.generated_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> BehavioralFeatures:
        from datetime import datetime as _dt

        def _to_dt(value):
            if isinstance(value, _dt):
                return value
            if isinstance(value, str):
                return _dt.fromisoformat(value.replace("Z", "+00:00"))
            return value

        return BehavioralFeatures(
            id=uuid.UUID(doc["_id"]) if isinstance(doc.get("_id"), str) else uuid.uuid4(),
            user_id=doc["user_id"],
            window=doc["window"],
            window_start=_to_dt(doc["window_start"]),
            window_end=_to_dt(doc["window_end"]),
            source_dataset=doc.get("source_dataset", "all"),
            features=dict(doc.get("features", {})),
            feature_version=doc.get("feature_version", FEATURE_VERSION),
            event_count=int(doc.get("event_count", 0)),
            generated_at=_to_dt(doc.get("generated_at")) or _dt.utcnow(),
        )

    async def upsert_many(self, features: Sequence[BehavioralFeatures]) -> int:
        if not features:
            return 0
        coll = self.db[self.COLLECTION]
        count = 0
        for f in features:
            doc = self._to_doc(f)
            # Idempotency: same (user, window, window_start, source) -> replace
            await coll.update_one(
                {
                    "user_id": f.user_id,
                    "window": f.window,
                    "window_start": f.window_start,
                    "source_dataset": f.source_dataset,
                    "feature_version": f.feature_version,
                },
                {"$set": doc},
                upsert=True,
            )
            count += 1
        return count

    async def list_for_user(
        self,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        source_dataset: str | None = None,
    ) -> list[BehavioralFeatures]:
        query: dict = {"user_id": user_id}
        if source_dataset is not None:
            query["source_dataset"] = source_dataset
        if start is not None or end is not None:
            ts_q: dict = {}
            if start is not None:
                ts_q["$gte"] = start
            if end is not None:
                ts_q["$lt"] = end
            query["window_start"] = ts_q
        cursor = self.db[self.COLLECTION].find(query).sort("window_start", 1)
        return [self._from_doc(doc) async for doc in cursor]

    async def list_users_with_features(
        self, source_dataset: str | None = None
    ) -> list[str]:
        query: dict = {}
        if source_dataset is not None:
            query["source_dataset"] = source_dataset
        return await self.db[self.COLLECTION].distinct("user_id", query)

    async def list_in_window(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        source_dataset: str | None = None,
    ) -> list[BehavioralFeatures]:
        """Phase 5: list all feature rows in [start, end) for training export."""
        query: dict = {}
        if source_dataset is not None:
            query["source_dataset"] = source_dataset
        if start is not None or end is not None:
            ts_q: dict = {}
            if start is not None:
                ts_q["$gte"] = start
            if end is not None:
                ts_q["$lt"] = end
            query["window_start"] = ts_q
        cursor = self.db[self.COLLECTION].find(query).sort("window_start", 1)
        return [self._from_doc(doc) async for doc in cursor]


# ─── Postgres baseline repository ────────────────────────────


class SQLBehavioralBaselineRepository(IBehavioralBaselineRepository):
    """SQLAlchemy implementation of IBehavioralBaselineRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _to_domain(self, m: BehavioralBaselineModel) -> BehavioralBaseline:
        return BehavioralBaseline(
            id=m.id,
            user_id=m.user_id,
            feature_version=m.feature_version,
            stats=dict(m.stats or {}),
            window_start=m.window_start,
            window_end=m.window_end,
            observation_days=int(m.observation_days),
            created_at=m.created_at,
            updated_at=m.updated_at,
            source_dataset=m.source_dataset or "all",
        )

    def _to_model(
        self,
        e: BehavioralBaseline,
        existing: BehavioralBaselineModel | None = None,
    ) -> BehavioralBaselineModel:
        m = existing or BehavioralBaselineModel(id=e.id)
        m.user_id = e.user_id
        m.feature_version = e.feature_version
        m.stats = dict(e.stats)
        m.window_start = e.window_start
        m.window_end = e.window_end
        m.observation_days = int(e.observation_days)
        m.created_at = e.created_at
        m.updated_at = e.updated_at
        m.source_dataset = e.source_dataset
        return m

    async def save(self, baseline: BehavioralBaseline) -> BehavioralBaseline:
        from datetime import datetime as _dt

        baseline.updated_at = _dt.now(UTC)
        stmt = select(BehavioralBaselineModel).where(
            BehavioralBaselineModel.user_id == baseline.user_id,
            BehavioralBaselineModel.feature_version == baseline.feature_version,
        )
        result = await self.session.execute(stmt)
        existing = result.scalars().first()
        model = self._to_model(baseline, existing)
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def get(
        self, user_id: str, feature_version: str
    ) -> BehavioralBaseline | None:
        stmt = select(BehavioralBaselineModel).where(
            BehavioralBaselineModel.user_id == user_id,
            BehavioralBaselineModel.feature_version == feature_version,
        )
        result = await self.session.execute(stmt)
        m = result.scalars().first()
        return self._to_domain(m) if m else None

    async def list_all(self) -> Sequence[BehavioralBaseline]:
        stmt = select(BehavioralBaselineModel).order_by(
            BehavioralBaselineModel.user_id
        )
        result = await self.session.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]
