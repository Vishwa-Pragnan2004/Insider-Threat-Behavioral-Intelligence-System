"""
ITBIS — Anomaly Module: MongoDB Result Store
"""
import uuid
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.anomaly.domain.entities import AnomalyResult, BehavioralDeviation
from app.modules.anomaly.domain.enums import AnomalyPrediction, RiskLevel
from app.modules.anomaly.domain.repositories import IAnomalyResultStore


class MongoAnomalyResultStore(IAnomalyResultStore):
    """MongoDB-backed persistence for AnomalyResult documents."""

    COLLECTION = "anomaly_results"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    @staticmethod
    def _to_doc(r: AnomalyResult) -> dict:
        return {
            "_id": str(r.id),
            "user_id": r.user_id,
            "source_dataset": r.source_dataset,
            "window": r.window,
            "window_start": r.window_start,
            "window_end": r.window_end,
            "model_version": r.model_version,
            "feature_version": r.feature_version,
            "prediction": r.prediction.value,
            "raw_anomaly_score": float(r.raw_anomaly_score),
            "risk_score": float(r.risk_score),
            "risk_level": r.risk_level.value,
            "top_behavioral_deviations": [
                {
                    "feature": d.feature,
                    "value": float(d.value),
                    "baseline_mean": float(d.baseline_mean),
                    "baseline_std": float(d.baseline_std),
                    "zscore": float(d.zscore),
                }
                for d in r.top_behavioral_deviations
            ],
            "model_input": {k: float(v) for k, v in r.model_input.items()},
            "baseline_source": r.baseline_source,
            "created_at": r.created_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> AnomalyResult:
        def _to_dt(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value

        deviations = [
            BehavioralDeviation(
                feature=d["feature"],
                value=float(d["value"]),
                baseline_mean=float(d["baseline_mean"]),
                baseline_std=float(d["baseline_std"]),
                zscore=float(d["zscore"]),
            )
            for d in doc.get("top_behavioral_deviations", []) or []
        ]
        return AnomalyResult(
            id=uuid.UUID(doc["_id"]) if isinstance(doc.get("_id"), str) else uuid.uuid4(),
            user_id=doc["user_id"],
            source_dataset=doc.get("source_dataset", "all"),
            window=doc.get("window", "daily"),
            window_start=_to_dt(doc["window_start"]),
            window_end=_to_dt(doc["window_end"]),
            model_version=doc.get("model_version", "unknown"),
            feature_version=doc.get("feature_version", "unknown"),
            prediction=AnomalyPrediction(doc.get("prediction", "normal")),
            raw_anomaly_score=float(doc.get("raw_anomaly_score", 0.0)),
            risk_score=float(doc.get("risk_score", 0.0)),
            risk_level=RiskLevel(doc.get("risk_level", "LOW")),
            top_behavioral_deviations=deviations,
            model_input=dict(doc.get("model_input", {}) or {}),
            baseline_source=doc.get("baseline_source", "global"),
            created_at=_to_dt(doc.get("created_at")) or datetime.now(tz=datetime.timezone.utc),
        )

    async def upsert(self, result: AnomalyResult) -> None:
        """
        Idempotent upsert keyed on (user_id, window, window_start).

        Uses the MongoDB $setOnInsert / $set pattern so the immutable
        ``_id`` is only written on first insert and never overwritten
        on subsequent updates.  This keeps the operation safe under
        repeated detection (the same window can be re-detected many
        times) and under real MongoDB's "immutable _id" semantics.
        """
        coll = self.db[self.COLLECTION]
        full_doc = self._to_doc(result)
        doc_id = full_doc.pop("_id")
        await coll.update_one(
            {
                "user_id": result.user_id,
                "window": result.window,
                "window_start": result.window_start,
            },
            {
                "$setOnInsert": {"_id": doc_id},
                "$set": full_doc,
            },
            upsert=True,
        )

    async def list_for_user(
        self,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
        risk_level: RiskLevel | None = None,
        limit: int = 100,
    ) -> list[AnomalyResult]:
        query: dict = {"user_id": user_id}
        if start is not None or end is not None:
            ts_q: dict = {}
            if start is not None:
                ts_q["$gte"] = start
            if end is not None:
                ts_q["$lt"] = end
            query["window_start"] = ts_q
        if risk_level is not None:
            query["risk_level"] = risk_level.value
        cursor = self.db[self.COLLECTION].find(query).sort("window_start", -1).limit(limit)
        return [self._from_doc(d) async for d in cursor]

    async def list_recent(
        self,
        risk_level: RiskLevel | None = None,
        prediction: AnomalyPrediction | None = None,
        limit: int = 100,
    ) -> list[AnomalyResult]:
        query: dict = {}
        if risk_level is not None:
            query["risk_level"] = risk_level.value
        if prediction is not None:
            query["prediction"] = prediction.value
        cursor = self.db[self.COLLECTION].find(query).sort("created_at", -1).limit(limit)
        return [self._from_doc(d) async for d in cursor]

    async def get_by_id(self, result_id: uuid.UUID) -> AnomalyResult | None:
        doc = await self.db[self.COLLECTION].find_one({"_id": str(result_id)})
        return self._from_doc(doc) if doc else None
