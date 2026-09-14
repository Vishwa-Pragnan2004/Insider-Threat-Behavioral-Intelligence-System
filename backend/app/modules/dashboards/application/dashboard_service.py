"""
ITBIS — Dashboards: role workspaces

Read-only aggregates for the three role dashboards in the specification:

    Security Analyst   threat alerts, insider risk scores, investigation queue,
                       incident summaries
    SOC Engineer       security events, behavioral anomalies, active
                       investigations, threat intelligence
    Security Manager   organisational risk posture, risk trends, insider threat
                       reports, compliance metrics

Everything is computed on request from the existing stores (alerts,
investigations, anomaly results and canonical events in MongoDB; baselines,
agent devices and the audit log in PostgreSQL). The module keeps no data of
its own.

"Active" alerts are those not yet closed out: OPEN, ACKNOWLEDGED or
IN_PROGRESS.
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.activity.application.event_queries import (
    EventQueries,
    as_utc,
    iso,
    timestamp_bound,
)
from app.modules.behavioral.infrastructure.models import BehavioralBaselineModel
from app.modules.identity.infrastructure.models import AgentDeviceModel, AuthAuditLogModel

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
INVESTIGATION_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED")
ACTIVE_ALERT_STATUSES = ["OPEN", "ACKNOWLEDGED", "IN_PROGRESS"]
ACTIVE_INVESTIGATION_STATUSES = ["OPEN", "IN_PROGRESS"]
HIGH_RISK_SCORE = 60.0
CRITICAL_SLA_HOURS = 24

THREAT_INTEL_NOTE = (
    "Indicators come from this organisation's own telemetry: risk indicators "
    "raised when agent and CERT events were collected, and connections to "
    "public internet addresses. No external threat-intelligence feed is connected."
)

_SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}


def _now() -> datetime:
    return datetime.now(UTC)


def _counts(counter: Counter, keys: tuple[str, ...]) -> dict[str, int]:
    return {key: int(counter.get(key, 0)) for key in keys}


def _pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def _mean_hours(durations: list[timedelta]) -> float | None:
    if not durations:
        return None
    return round(statistics.fmean(d.total_seconds() for d in durations) / 3600, 2)


def _alert_brief(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "user_id": doc.get("user_id", "unknown"),
        "severity": doc.get("severity", "LOW"),
        "status": doc.get("status", "OPEN"),
        "risk_score": float(doc.get("risk_score") or 0.0),
        "created_at": iso(doc.get("created_at")),
    }


def _investigation_brief(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "title": doc.get("title", ""),
        "severity": doc.get("severity", "MEDIUM"),
        "status": doc.get("status", "OPEN"),
        "assigned_to": doc.get("assigned_to"),
        "related_user_ids": list(doc.get("related_user_ids") or []),
        "created_at": iso(doc.get("created_at")),
        "updated_at": iso(doc.get("updated_at")),
    }


def _most_urgent_first(doc: dict) -> tuple:
    changed = as_utc(doc.get("updated_at") or doc.get("created_at")) or datetime.min.replace(
        tzinfo=UTC
    )
    return (-_SEVERITY_RANK.get(doc.get("severity", "LOW"), 0), -changed.timestamp())


def _top_deviation(doc: dict) -> str | None:
    deviations = doc.get("top_behavioral_deviations") or []
    if not deviations:
        return None
    top = deviations[0]
    return f"{top.get('feature')} (z={float(top.get('zscore') or 0.0):+.1f})"


class DashboardService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        session: AsyncSession,
        *,
        pipeline_status: Any = None,
        now: datetime | None = None,
    ) -> None:
        self._db = db
        self._session = session
        self._pipeline_status = pipeline_status
        self._now = as_utc(now) or _now()

    # ─── Security Analyst ───────────────────────────────────

    async def analyst(self, *, viewer_id: str) -> dict:
        now = self._now
        alerts = self._db["alerts"]

        active = [d async for d in alerts.find({"status": {"$in": ACTIVE_ALERT_STATUSES}})]
        open_by_severity = Counter(d.get("severity") for d in active)
        new_last_24h = await alerts.count_documents(
            {"created_at": {"$gte": now - timedelta(hours=24)}}
        )

        investigations = [d async for d in self._db["investigations"].find({})]
        queue = sorted(
            (d for d in investigations if d.get("status") in ACTIVE_INVESTIGATION_STATUSES),
            key=_most_urgent_first,
        )

        incident_since = now - timedelta(days=30)
        resolved = await alerts.count_documents(
            {"status": "RESOLVED", "updated_at": {"$gte": incident_since}}
        )
        false_positives = await alerts.count_documents(
            {"status": "FALSE_POSITIVE", "updated_at": {"$gte": incident_since}}
        )
        closed = sorted(
            (
                d
                for d in investigations
                if d.get("status") in ("RESOLVED", "CLOSED")
                and (as_utc(d.get("closed_at") or d.get("updated_at")) or now) >= incident_since
            ),
            key=lambda d: as_utc(d.get("closed_at") or d.get("updated_at")) or now,
            reverse=True,
        )

        return {
            "generated_at": iso(now),
            "threat_alerts": {
                "open_total": len(active),
                "open_by_severity": _counts(open_by_severity, SEVERITIES),
                "new_last_24h": new_last_24h,
                "recent": [_alert_brief(d) for d in sorted(active, key=_most_urgent_first)[:10]],
            },
            "insider_risk": {
                "window_days": 7,
                "users": (await self._user_risks(now - timedelta(days=7)))[:10],
            },
            "investigation_queue": {
                "counts_by_status": _counts(
                    Counter(d.get("status") for d in investigations), INVESTIGATION_STATUSES
                ),
                "assigned_to_me": [
                    _investigation_brief(d) for d in queue if d.get("assigned_to") == viewer_id
                ][:10],
                "unassigned": [_investigation_brief(d) for d in queue if not d.get("assigned_to")][
                    :10
                ],
            },
            "incident_summaries": {
                "window_days": 30,
                "resolved": resolved,
                "false_positives": false_positives,
                "recent": [
                    {
                        "id": str(d["_id"]),
                        "title": d.get("title", ""),
                        "severity": d.get("severity", "MEDIUM"),
                        "status": d.get("status"),
                        "resolution": d.get("resolution"),
                        "closed_at": iso(d.get("closed_at")),
                        "related_user_ids": list(d.get("related_user_ids") or []),
                    }
                    for d in closed[:8]
                ],
            },
        }

    # ─── SOC Engineer ───────────────────────────────────────

    async def soc(self) -> dict:
        now = self._now
        events = EventQueries(self._db)
        week_ago = now - timedelta(days=7)

        results = [
            d async for d in self._db["anomaly_results"].find({"window_start": {"$gte": week_ago}})
        ]
        anomalies = sorted(
            (d for d in results if d.get("prediction") == "anomaly"),
            key=lambda d: as_utc(d.get("window_start")) or now,
            reverse=True,
        )

        investigations = [
            d
            async for d in self._db["investigations"].find(
                {"status": {"$in": ACTIVE_INVESTIGATION_STATUSES}}
            )
        ]
        all_statuses = Counter(
            [d.get("status") async for d in self._db["investigations"].find({}, {"status": 1})]
        )

        return {
            "generated_at": iso(now),
            "security_events": {
                **await events.summary(hours=24, now=now),
                "recent": await events.recent(15),
            },
            "behavioral_anomalies": {
                "window_days": 7,
                "results": len(results),
                "anomalies": len(anomalies),
                "by_risk_level": _counts(Counter(d.get("risk_level") for d in results), SEVERITIES),
                "recent": [
                    {
                        "id": str(d["_id"]),
                        "user_id": d.get("user_id", "unknown"),
                        "window_start": iso(d.get("window_start")),
                        "risk_score": float(d.get("risk_score") or 0.0),
                        "risk_level": d.get("risk_level", "LOW"),
                        "prediction": d.get("prediction", "anomaly"),
                        "baseline_source": d.get("baseline_source", "global"),
                        "top_deviation": _top_deviation(d),
                    }
                    for d in anomalies[:10]
                ],
            },
            "active_investigations": {
                "counts_by_status": _counts(all_statuses, INVESTIGATION_STATUSES),
                "items": [
                    _investigation_brief(d) for d in sorted(investigations, key=_most_urgent_first)
                ][:10],
            },
            "threat_intelligence": {
                "window_days": 7,
                "note": THREAT_INTEL_NOTE,
                **await self._internal_indicators(events, week_ago),
                "pipeline": self._pipeline(),
            },
        }

    async def _internal_indicators(self, events: EventQueries, since: datetime) -> dict:
        bound = timestamp_bound(since)
        indicator_counts: Counter[str] = Counter()
        last_seen: dict[str, datetime] = {}
        flagged = events.find(
            {"timestamp": {"$gte": bound}, "risk_indicators": {"$exists": True, "$ne": []}},
            {"risk_indicators": 1, "timestamp": 1},
        )
        async for doc in flagged:
            when = as_utc(doc.get("timestamp"))
            for indicator in doc.get("risk_indicators") or []:
                indicator_counts[indicator] += 1
                if when and (indicator not in last_seen or when > last_seen[indicator]):
                    last_seen[indicator] = when

        destinations: Counter[str] = Counter()
        destination_users: dict[str, set[str]] = {}
        public = events.find(
            {
                "timestamp": {"$gte": bound},
                "event_type": "network_connection",
                "enrichments.remote_scope": "public",
            },
            {"enrichments": 1, "target_resource": 1, "user_id": 1},
        )
        async for doc in public:
            enrichments = doc.get("enrichments") or {}
            destination = str(enrichments.get("remote_address") or doc.get("target_resource"))
            destinations[destination] += 1
            destination_users.setdefault(destination, set()).add(doc.get("user_id") or "unknown")

        return {
            "indicators": [
                {"indicator": name, "count": count, "last_seen": iso(last_seen.get(name))}
                for name, count in indicator_counts.most_common(15)
            ],
            "external_destinations": [
                {"destination": name, "count": count, "users": len(destination_users[name])}
                for name, count in destinations.most_common(10)
            ],
        }

    def _pipeline(self) -> dict:
        status = self._pipeline_status
        last_run = getattr(status, "last_run", None)
        return {
            "scheduler_enabled": bool(getattr(status, "scheduler_enabled", False)),
            "running": bool(getattr(status, "running", False)),
            "last_success_at": iso(getattr(status, "last_success_at", None)),
            "next_run_at": iso(getattr(status, "next_run_at", None)),
            "last_error": getattr(last_run, "error", None),
        }

    # ─── Security Manager ───────────────────────────────────

    async def manager(self) -> dict:
        now = self._now
        since = now - timedelta(days=30)
        alerts = self._db["alerts"]

        recent_alerts = [d async for d in alerts.find({"created_at": {"$gte": since}})]
        recent_investigations = [
            d async for d in self._db["investigations"].find({"created_at": {"$gte": since}})
        ]
        baselined = set(
            (await self._session.execute(select(distinct(BehavioralBaselineModel.user_id))))
            .scalars()
            .all()
        )

        # Prefer the weighted insider risk scores; before the risk engine has
        # scored anyone, fall back to the behavioral model's results.
        scores = [d async for d in self._db["employee_risk_scores"].find({"day": {"$gte": since}})]
        if scores:
            source = "weighted_risk"
            risks, latest_high = self._weighted_risks(scores)
            series = self._weighted_series(scores, recent_alerts)
        else:
            source = "behavioral_model"
            risks = await self._user_risks(since)
            latest_high = sum(1 for r in risks if r["latest_risk_score"] >= HIGH_RISK_SCORE)
            results = [
                d
                async for d in self._db["anomaly_results"].find(
                    {"window_start": {"$gte": since}},
                    {"window_start": 1, "risk_score": 1, "prediction": 1},
                )
            ]
            series = self._daily_series(results, recent_alerts)
        monitored = {r["user_id"] for r in risks}
        latest_scores = [r["latest_risk_score"] for r in risks]

        return {
            "generated_at": iso(now),
            "risk_posture": {
                "risk_source": source,
                "monitored_users": len(monitored),
                "baselined_users": len(monitored & baselined),
                "learning_users": len(monitored - baselined),
                "high_risk_users": latest_high,
                "org_risk_index": (
                    round(statistics.fmean(latest_scores), 1) if latest_scores else None
                ),
                "open_critical_alerts": await alerts.count_documents(
                    {"status": {"$in": ACTIVE_ALERT_STATUSES}, "severity": "CRITICAL"}
                ),
                "open_investigations": await self._db["investigations"].count_documents(
                    {"status": {"$in": ACTIVE_INVESTIGATION_STATUSES}}
                ),
            },
            "risk_trends": {"days": 30, "series": series},
            "insider_threat_report": {
                "window_days": 30,
                "top_users": risks[:10],
                "alerts_by_severity": _counts(
                    Counter(d.get("severity") for d in recent_alerts), SEVERITIES
                ),
                "investigations_by_status": _counts(
                    Counter(d.get("status") for d in recent_investigations), INVESTIGATION_STATUSES
                ),
            },
            "compliance": await self._compliance(recent_alerts, recent_investigations, since),
        }

    @staticmethod
    def _weighted_risks(scores: list[dict]) -> tuple[list[dict], int]:
        """
        Per-employee risk from daily weighted scores, highest priority first,
        and how many employees' latest priority is HIGH or above.

        Same row shape as the behavioral-model version: `anomalies` counts
        high-priority days and `results` the days scored.
        """
        users: dict[str, dict] = {}
        for doc in sorted(
            scores, key=lambda d: as_utc(d.get("day")) or datetime.min.replace(tzinfo=UTC)
        ):
            user_id = doc.get("user_id") or "unknown"
            score = float(doc.get("score") or 0.0)
            priority = float(doc.get("priority") or 0.0)
            entry = users.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "latest_risk_score": score,
                    "max_risk_score": score,
                    "risk_level": doc.get("level", "LOW"),
                    "anomalies": 0,
                    "results": 0,
                    "last_scored_at": None,
                    "baseline_source": "personal",
                    "latest_priority": priority,
                    "max_priority": priority,
                },
            )
            entry["results"] += 1
            if priority >= HIGH_RISK_SCORE:
                entry["anomalies"] += 1
            entry["max_risk_score"] = max(entry["max_risk_score"], score)
            entry["max_priority"] = max(entry["max_priority"], priority)
            entry["latest_risk_score"] = score
            entry["latest_priority"] = priority
            entry["risk_level"] = doc.get("level", "LOW")
            entry["last_scored_at"] = iso(doc.get("day"))
        ranked = sorted(
            users.values(), key=lambda e: (e["max_priority"], e["max_risk_score"]), reverse=True
        )
        high = sum(1 for e in ranked if e["latest_priority"] >= HIGH_RISK_SCORE)
        return ranked, high

    def _weighted_series(self, scores: list[dict], alerts: list[dict]) -> list[dict]:
        """Daily average / maximum weighted score and employees at HIGH+ priority."""
        today = self._now.date()
        days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
        by_day: dict = {day: [] for day in days}
        high: Counter = Counter()
        for doc in scores:
            when = as_utc(doc.get("day"))
            if when is None or when.date() not in by_day:
                continue
            by_day[when.date()].append(float(doc.get("score") or 0.0))
            if float(doc.get("priority") or 0.0) >= HIGH_RISK_SCORE:
                high[when.date()] += 1
        created = Counter(
            when.date() for when in (as_utc(d.get("created_at")) for d in alerts) if when
        )
        return [
            {
                "date": day.isoformat(),
                "avg_risk_score": round(statistics.fmean(by_day[day]), 1) if by_day[day] else None,
                "max_risk_score": round(max(by_day[day]), 1) if by_day[day] else None,
                "anomalies": high[day],
                "alerts_created": created[day],
            }
            for day in days
        ]

    def _daily_series(self, results: list[dict], alerts: list[dict]) -> list[dict]:
        today = self._now.date()
        days = [today - timedelta(days=offset) for offset in range(29, -1, -1)]
        scores: dict = {day: [] for day in days}
        anomalies: Counter = Counter()
        for doc in results:
            when = as_utc(doc.get("window_start"))
            if when is None or when.date() not in scores:
                continue
            scores[when.date()].append(float(doc.get("risk_score") or 0.0))
            if doc.get("prediction") == "anomaly":
                anomalies[when.date()] += 1
        created = Counter(
            when.date() for when in (as_utc(d.get("created_at")) for d in alerts) if when
        )
        return [
            {
                "date": day.isoformat(),
                "avg_risk_score": round(statistics.fmean(scores[day]), 1) if scores[day] else None,
                "max_risk_score": round(max(scores[day]), 1) if scores[day] else None,
                "anomalies": anomalies[day],
                "alerts_created": created[day],
            }
            for day in days
        ]

    async def _compliance(
        self, alerts: list[dict], investigations: list[dict], since: datetime
    ) -> dict:
        now = self._now
        to_acknowledge: list[timedelta] = []
        to_resolve: list[timedelta] = []
        critical_due = critical_on_time = 0
        for doc in alerts:
            created = as_utc(doc.get("created_at"))
            acknowledged = as_utc(doc.get("acknowledged_at"))
            resolved = as_utc(doc.get("resolved_at"))
            if created and acknowledged:
                to_acknowledge.append(acknowledged - created)
            if created and resolved:
                to_resolve.append(resolved - created)
            if doc.get("severity") == "CRITICAL" and created:
                deadline = created + timedelta(hours=CRITICAL_SLA_HOURS)
                # Only alerts whose deadline has passed, or that were already
                # acknowledged, can be judged against the SLA.
                if acknowledged or deadline <= now:
                    critical_due += 1
                    if acknowledged and acknowledged <= deadline:
                        critical_on_time += 1

        devices = (
            (
                await self._session.execute(
                    select(AgentDeviceModel.last_seen_at).where(
                        AgentDeviceModel.is_active.is_(True), AgentDeviceModel.revoked_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        reporting = sum(1 for seen in devices if seen and as_utc(seen) >= now - timedelta(hours=24))
        admin_actions = (
            await self._session.execute(
                select(func.count())
                .select_from(AuthAuditLogModel)
                .where(
                    AuthAuditLogModel.actor_user_id.is_not(None),
                    AuthAuditLogModel.occurred_at >= since,
                )
            )
        ).scalar_one()

        return {
            "window_days": 30,
            "alerts_total": len(alerts),
            "triaged_pct": _pct(sum(1 for d in alerts if d.get("status") != "OPEN"), len(alerts)),
            "mean_hours_to_acknowledge": _mean_hours(to_acknowledge),
            "mean_hours_to_resolve": _mean_hours(to_resolve),
            "critical_sla_hours": CRITICAL_SLA_HOURS,
            "critical_within_sla_pct": _pct(critical_on_time, critical_due),
            "investigations_closed_pct": _pct(
                sum(1 for d in investigations if d.get("status") in ("RESOLVED", "CLOSED")),
                len(investigations),
            ),
            "devices_enrolled": len(devices),
            "devices_reporting_24h": reporting,
            "agent_coverage_pct": _pct(reporting, len(devices)),
            "admin_actions": int(admin_actions),
        }

    # ─── Shared ─────────────────────────────────────────────

    async def _user_risks(self, since: datetime) -> list[dict]:
        """Per-user risk from anomaly results since `since`, riskiest first."""
        users: dict[str, dict] = {}
        cursor = self._db["anomaly_results"].find(
            {"window_start": {"$gte": since}},
            {
                "user_id": 1,
                "window_start": 1,
                "risk_score": 1,
                "risk_level": 1,
                "prediction": 1,
                "baseline_source": 1,
            },
        )
        async for doc in cursor:
            user_id = doc.get("user_id") or "unknown"
            when = as_utc(doc.get("window_start")) or since
            score = float(doc.get("risk_score") or 0.0)
            entry = users.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "latest_risk_score": score,
                    "max_risk_score": score,
                    "risk_level": doc.get("risk_level", "LOW"),
                    "anomalies": 0,
                    "results": 0,
                    "last_scored_at": when,
                    "baseline_source": doc.get("baseline_source", "global"),
                },
            )
            entry["results"] += 1
            if doc.get("prediction") == "anomaly":
                entry["anomalies"] += 1
            if score > entry["max_risk_score"] or entry["results"] == 1:
                entry["max_risk_score"] = score
                entry["risk_level"] = doc.get("risk_level", "LOW")
            if when >= entry["last_scored_at"]:
                entry["last_scored_at"] = when
                entry["latest_risk_score"] = score
                entry["baseline_source"] = doc.get("baseline_source", "global")

        ranked = sorted(
            users.values(),
            key=lambda e: (e["max_risk_score"], e["last_scored_at"]),
            reverse=True,
        )
        for entry in ranked:
            entry["last_scored_at"] = iso(entry["last_scored_at"])
        return ranked
