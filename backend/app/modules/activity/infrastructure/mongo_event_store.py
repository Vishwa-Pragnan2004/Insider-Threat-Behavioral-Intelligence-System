"""
ITBIS — Activity Module: MongoDB Activity Event Store
Persists normalised CanonicalEvent documents to MongoDB.
"""
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.activity.domain.repositories import IActivityEventStore
from app.shared.schemas.canonical_event import CanonicalEvent


class MongoActivityEventStore(IActivityEventStore):
    """Motor-based implementation of IActivityEventStore."""

    COLLECTION = "canonical_events"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    @staticmethod
    def _serialize(event: CanonicalEvent | dict, job_id: str | None = None) -> dict:
        if isinstance(event, CanonicalEvent):
            doc = event.model_dump(mode="json")
        else:
            doc = dict(event)
        doc.setdefault("ingested_at", datetime.now(UTC).isoformat())
        if job_id is not None:
            doc["job_id"] = job_id
        return doc

    async def insert_many(
        self,
        events: Sequence[dict | CanonicalEvent],
        job_id: str | None = None,
    ) -> int:
        if not events:
            return 0
        docs = [self._serialize(e, job_id=job_id) for e in events]
        result = await self.db[self.COLLECTION].insert_many(docs, ordered=False)
        return len(result.inserted_ids)

    async def count_for_job(self, job_id: str) -> int:
        return await self.db[self.COLLECTION].count_documents({"job_id": job_id})

    async def delete_for_job(self, job_id: str) -> int:
        """Remove all events for a given job (used by tests / reprocessing)."""
        result = await self.db[self.COLLECTION].delete_many({"job_id": job_id})
        return result.deleted_count

    # ─── Read APIs (added Phase 4) ────────────────────────────
    #
    # These support the behavioral feature engineering pipeline.  They are
    # additive — no existing method changes.

    async def find_events(
        self,
        *,
        user_id: Optional[str] = None,
        source_dataset: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100_000,
    ) -> list[dict]:
        """Find canonical events matching the given filters.

        Returns raw documents sorted by timestamp ascending.  Used by the
        Phase 4 feature engineering pipeline; no other module depends on
        this shape.
        """
        query: dict = {}
        if user_id is not None:
            query["user_id"] = user_id
        if source_dataset is not None:
            query["source_dataset"] = source_dataset
        if start is not None or end is not None:
            ts_query: dict = {}
            if start is not None:
                # Query with the ISO representation: the canonical event
                # pipeline (`model_dump(mode="json")`) stores timestamps as
                # ISO strings, so range queries must also use ISO strings
                # to avoid BSON type-mismatch.
                ts_query["$gte"] = start.isoformat()
            if end is not None:
                ts_query["$lt"] = end.isoformat()
            query["timestamp"] = ts_query

        cursor = (
            self.db[self.COLLECTION]
            .find(query)
            .sort("timestamp", 1)
            .limit(limit)
        )
        return [doc async for doc in cursor]
