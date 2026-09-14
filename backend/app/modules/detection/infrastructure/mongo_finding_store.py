"""
ITBIS — Detection Module: MongoDB finding store
"""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.detection.domain.categories import AnomalyCategory, DetectionEngine
from app.modules.detection.domain.finding import Finding


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class MongoFindingStore:
    COLLECTION = "detection_findings"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._indexes_built = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_built:
            return
        coll = self.db[self.COLLECTION]
        await coll.create_index("key", unique=True, name="ux_finding_key")
        await coll.create_index([("user_id", 1), ("day", -1)], name="ix_finding_user_day")
        await coll.create_index([("day", -1)], name="ix_finding_day")
        await coll.create_index("category", name="ix_finding_category")
        self._indexes_built = True

    @staticmethod
    def _to_doc(f: Finding) -> dict:
        return {
            "_id": str(f.id),
            "key": f.key,
            "user_id": f.user_id,
            "day": f.day,
            "category": f.category.value,
            "engine": f.engine.value,
            "detector": f.detector,
            "severity": f.severity,
            "title": f.title,
            "description": f.description,
            "evidence": f.evidence,
            "event_ids": f.event_ids,
            "source_dataset": f.source_dataset,
            "detector_version": f.detector_version,
            "created_at": f.created_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> Finding:
        return Finding(
            user_id=doc["user_id"],
            day=_as_utc(doc["day"]),
            category=AnomalyCategory(doc["category"]),
            detector=doc["detector"],
            severity=float(doc.get("severity") or 0.0),
            title=doc.get("title", ""),
            description=doc.get("description", ""),
            evidence=dict(doc.get("evidence") or {}),
            event_ids=list(doc.get("event_ids") or []),
            source_dataset=doc.get("source_dataset", "all"),
            detector_version=doc.get("detector_version", "unknown"),
            created_at=_as_utc(doc.get("created_at")) or datetime.now(UTC),
        )

    async def replace_for_user_days(
        self, user_id: str, start: datetime, end: datetime, findings: list[Finding]
    ) -> None:
        """
        Make the stored findings for `user_id` on days in [start, end) exactly
        `findings`: upsert them and drop ones that no longer apply (e.g. the
        day's later events showed a spike was ordinary after all).
        """
        await self._ensure_indexes()
        coll = self.db[self.COLLECTION]
        keys = [f.key for f in findings]
        await coll.delete_many(
            {"user_id": user_id, "day": {"$gte": start, "$lt": end}, "key": {"$nin": keys}}
        )
        for finding in findings:
            doc = self._to_doc(finding)
            doc_id = doc.pop("_id")
            created = doc.pop("created_at")
            await coll.update_one(
                {"key": finding.key},
                {"$set": doc, "$setOnInsert": {"_id": doc_id, "created_at": created}},
                upsert=True,
            )

    async def list_findings(
        self,
        *,
        user_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        category: AnomalyCategory | None = None,
        engine: DetectionEngine | None = None,
        min_severity: float | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Finding], int]:
        query: dict = {}
        if user_id:
            query["user_id"] = user_id
        if start or end:
            query["day"] = {}
            if start:
                query["day"]["$gte"] = start
            if end:
                query["day"]["$lt"] = end
        if category:
            query["category"] = category.value
        if engine:
            query["engine"] = engine.value
        if min_severity is not None:
            query["severity"] = {"$gte": min_severity}
        coll = self.db[self.COLLECTION]
        total = await coll.count_documents(query)
        cursor = coll.find(query).sort([("day", -1), ("severity", -1)]).skip(skip).limit(limit)
        return [self._from_doc(d) async for d in cursor], total
