"""
ITBIS — Risk Module: where risk signals come from

    behavioral anomalies        detector findings in that component, plus the
                                ML model's anomalous days — only those scored
                                against the person's own baseline (the same
                                learning-period rule alerts follow)
    privilege / data / access   detector findings
    historical security events  past alerts an analyst engaged with (not
                                dismissed as false positives) and
                                investigations the person was part of

Alerts nobody has acted on yet don't count as history: otherwise the risk
engine's own alerts would raise tomorrow's score, and so on.
"""

from __future__ import annotations

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.detection.domain.categories import AnomalyCategory
from app.modules.detection.infrastructure.mongo_finding_store import MongoFindingStore
from app.modules.risk.application.scoring import signals_from_findings
from app.modules.risk.domain.model import RiskComponent, RiskSignal

ALERT_HISTORY_STATUSES = ["ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED"]
INVESTIGATION_HISTORY_STATUSES = ["IN_PROGRESS", "RESOLVED", "CLOSED"]
SEVERITY_WEIGHT = {"LOW": 30.0, "MEDIUM": 50.0, "HIGH": 70.0, "CRITICAL": 90.0}


def _as_utc(value) -> datetime | None:  # noqa: ANN001
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class MongoRiskSignalSource:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db
        self._findings = MongoFindingStore(db)

    async def signals_for(self, user_id: str, start: datetime, end: datetime) -> list[RiskSignal]:
        findings, _ = await self._findings.list_findings(
            user_id=user_id, start=start, end=end, limit=10_000
        )
        signals = signals_from_findings(findings)

        async for doc in self.db["anomaly_results"].find(
            {
                "user_id": user_id,
                "window_start": {"$gte": start, "$lt": end},
                "prediction": "anomaly",
                "baseline_source": "personal",
            }
        ):
            signals.append(
                RiskSignal(
                    day=_as_utc(doc["window_start"]),
                    component=RiskComponent.BEHAVIORAL_ANOMALIES,
                    severity=float(doc.get("risk_score") or 0.0),
                    label="Behavioral model: unusual day for this person",
                    category=AnomalyCategory.BEHAVIORAL_ANOMALY,
                    reference=str(doc["_id"]),
                )
            )

        async for doc in self.db["alerts"].find(
            {
                "user_id": user_id,
                "status": {"$in": ALERT_HISTORY_STATUSES},
                "created_at": {"$gte": start, "$lt": end},
            }
        ):
            when = _as_utc(doc.get("window_start")) or _as_utc(doc.get("created_at"))
            if when:
                signals.append(
                    RiskSignal(
                        day=when,
                        component=RiskComponent.HISTORICAL_SECURITY_EVENTS,
                        severity=SEVERITY_WEIGHT.get(doc.get("severity"), 50.0),
                        label=f"Past alert: {doc.get('title', '')}",
                        reference=str(doc["_id"]),
                    )
                )

        async for doc in self.db["investigations"].find(
            {
                "related_user_ids": user_id,
                "status": {"$in": INVESTIGATION_HISTORY_STATUSES},
                "created_at": {"$gte": start, "$lt": end},
            }
        ):
            when = _as_utc(doc.get("created_at"))
            if when:
                signals.append(
                    RiskSignal(
                        day=when,
                        component=RiskComponent.HISTORICAL_SECURITY_EVENTS,
                        severity=SEVERITY_WEIGHT.get(doc.get("severity"), 50.0) + 10.0,
                        label=f"Investigation: {doc.get('title', '')}",
                        reference=str(doc["_id"]),
                    )
                )
        return signals
