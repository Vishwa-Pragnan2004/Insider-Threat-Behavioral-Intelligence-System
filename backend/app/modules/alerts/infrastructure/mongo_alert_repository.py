"""
ITBIS — Alerts Module: MongoDB Alert Repository
"""
import uuid
from datetime import datetime

import structlog
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.alerts.domain.entities import Alert, AlertDeviation
from app.modules.alerts.domain.enums import AlertSeverity, AlertStatus
from app.modules.alerts.domain.repositories import IAlertRepository

log = structlog.get_logger(__name__)


class MongoAlertRepository(IAlertRepository):
    """
    MongoDB-backed persistence for Alert.

    Indexes (created on first use):
      - `idempotency_key` UNIQUE   — enforces dedup atomically
      - `user_id`                 — alert listing
      - `status`                   — workflow filtering
      - `severity`                 — triage dashboards
      - `created_at`               — chronological listing
      - `investigation_id`         — investigation drill-down
      - `(user_id, status)`         — common composite query
    """

    COLLECTION = "alerts"

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._indexes_built = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_built:
            return
        coll = self.db[self.COLLECTION]
        await coll.create_index("idempotency_key", unique=True, name="ux_idem_key")
        await coll.create_index("user_id", name="ix_user_id")
        await coll.create_index("status", name="ix_status")
        await coll.create_index("severity", name="ix_severity")
        await coll.create_index("created_at", name="ix_created_at")
        await coll.create_index("investigation_id", name="ix_investigation_id")
        await coll.create_index(
            [("user_id", 1), ("status", 1)], name="ix_user_status"
        )
        self._indexes_built = True

    @staticmethod
    def _to_doc(a: Alert) -> dict:
        return {
            "_id": str(a.id),
            "idempotency_key": a.idempotency_key,
            "anomaly_result_id": str(a.anomaly_result_id),
            "user_id": a.user_id,
            "source_dataset": a.source_dataset,
            "window": a.window,
            "window_start": a.window_start,
            "window_end": a.window_end,
            "model_version": a.model_version,
            "feature_version": a.feature_version,
            "title": a.title,
            "description": a.description,
            "risk_score": float(a.risk_score),
            "risk_level": a.risk_level,
            "severity": a.severity.value,
            "status": a.status.value,
            "top_behavioral_deviations": [
                {
                    "feature": d.feature,
                    "value": float(d.value),
                    "baseline_mean": float(d.baseline_mean),
                    "baseline_std": float(d.baseline_std),
                    "zscore": float(d.zscore),
                }
                for d in a.top_behavioral_deviations
            ],
            "assigned_to": a.assigned_to,
            "investigation_id": str(a.investigation_id) if a.investigation_id else None,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }

    @staticmethod
    def _from_doc(doc: dict) -> Alert:
        def _to_dt(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value

        return Alert(
            id=uuid.UUID(doc["_id"]) if isinstance(doc.get("_id"), str) else uuid.uuid4(),
            idempotency_key=doc["idempotency_key"],
            anomaly_result_id=uuid.UUID(doc["anomaly_result_id"]),
            user_id=doc["user_id"],
            source_dataset=doc.get("source_dataset", "all"),
            window=doc.get("window", "daily"),
            window_start=_to_dt(doc["window_start"]),
            window_end=_to_dt(doc["window_end"]),
            model_version=doc.get("model_version", "unknown"),
            feature_version=doc.get("feature_version", "unknown"),
            title=doc["title"],
            description=doc["description"],
            risk_score=float(doc["risk_score"]),
            risk_level=doc.get("risk_level", "UNKNOWN"),
            severity=AlertSeverity(doc["severity"]),
            status=AlertStatus(doc["status"]),
            top_behavioral_deviations=[
                AlertDeviation(
                    feature=d["feature"],
                    value=float(d["value"]),
                    baseline_mean=float(d["baseline_mean"]),
                    baseline_std=float(d["baseline_std"]),
                    zscore=float(d["zscore"]),
                )
                for d in doc.get("top_behavioral_deviations", []) or []
            ],
            assigned_to=doc.get("assigned_to"),
            investigation_id=(
                uuid.UUID(doc["investigation_id"])
                if doc.get("investigation_id")
                else None
            ),
            created_at=_to_dt(doc.get("created_at")),
            updated_at=_to_dt(doc.get("updated_at")),
        )

    async def upsert(self, alert: Alert) -> tuple[Alert, bool]:
        await self._ensure_indexes()
        coll = self.db[self.COLLECTION]
        # Atomic dedup: insert with the unique idempotency_key.  If the
        # key already exists, fall back to fetching the existing doc.
        try:
            await coll.insert_one(self._to_doc(alert))
            return alert, True
        except Exception:  # noqa: BLE001
            # DuplicateKeyError or generic.  Fall through to fetch.
            existing = await coll.find_one({"idempotency_key": alert.idempotency_key})
            if existing is None:
                # Different error — re-raise.
                raise
            log.debug(
                "alerts.duplicate_idempotency_key",
                key=alert.idempotency_key,
                user_id=alert.user_id,
            )
            return self._from_doc(existing), False

    async def get_by_id(self, alert_id: uuid.UUID) -> Alert | None:
        await self._ensure_indexes()
        doc = await self.db[self.COLLECTION].find_one({"_id": str(alert_id)})
        return self._from_doc(doc) if doc else None

    async def _build_query(
        self,
        *,
        status: AlertStatus | None,
        severity: AlertSeverity | None,
        user_id: str | None,
        assigned_to: str | None,
        risk_level: str | None,
        source_dataset: str | None,
        investigation_id: uuid.UUID | None,
        start: datetime | None,
        end: datetime | None,
    ) -> dict:
        q: dict = {}
        if status is not None:
            q["status"] = status.value
        if severity is not None:
            q["severity"] = severity.value
        if user_id is not None:
            q["user_id"] = user_id
        if assigned_to is not None:
            q["assigned_to"] = assigned_to
        if risk_level is not None:
            q["risk_level"] = risk_level
        if source_dataset is not None:
            q["source_dataset"] = source_dataset
        if investigation_id is not None:
            q["investigation_id"] = str(investigation_id)
        if start is not None or end is not None:
            ts_q: dict = {}
            if start is not None:
                ts_q["$gte"] = start
            if end is not None:
                ts_q["$lt"] = end
            q["created_at"] = ts_q
        return q

    async def list_alerts(
        self,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        user_id: str | None = None,
        assigned_to: str | None = None,
        risk_level: str | None = None,
        source_dataset: str | None = None,
        investigation_id: uuid.UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Alert]:
        await self._ensure_indexes()
        q = await self._build_query(
            status=status,
            severity=severity,
            user_id=user_id,
            assigned_to=assigned_to,
            risk_level=risk_level,
            source_dataset=source_dataset,
            investigation_id=investigation_id,
            start=start,
            end=end,
        )
        cursor = (
            self.db[self.COLLECTION]
            .find(q)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [self._from_doc(d) async for d in cursor]

    async def count_alerts(
        self,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        user_id: str | None = None,
        assigned_to: str | None = None,
        risk_level: str | None = None,
        source_dataset: str | None = None,
        investigation_id: uuid.UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        await self._ensure_indexes()
        q = await self._build_query(
            status=status,
            severity=severity,
            user_id=user_id,
            assigned_to=assigned_to,
            risk_level=risk_level,
            source_dataset=source_dataset,
            investigation_id=investigation_id,
            start=start,
            end=end,
        )
        return int(await self.db[self.COLLECTION].count_documents(q))

    async def update(self, alert: Alert) -> Alert:
        await self._ensure_indexes()
        from datetime import UTC

        alert.updated_at = datetime.now(UTC)
        await self.db[self.COLLECTION].update_one(
            {"_id": str(alert.id)},
            {
                "$set": {
                    "status": alert.status.value,
                    "assigned_to": alert.assigned_to,
                    "investigation_id": (
                        str(alert.investigation_id) if alert.investigation_id else None
                    ),
                    "updated_at": alert.updated_at,
                }
            },
        )
        return alert
