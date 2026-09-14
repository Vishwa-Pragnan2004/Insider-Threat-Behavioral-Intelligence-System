"""
ITBIS — Integration tests: activity events API and role dashboards.

Covers:
  - collected events are browsable (the agent's logs were stored but never shown)
  - event filters, newest-first paging and the 24-hour summary
  - each role reaches its own dashboard and is refused the others
  - the headline figures on each dashboard, from seeded alerts, investigations,
    anomaly results and events
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.enums import RoleName
from app.modules.identity.infrastructure.repositories import (
    SQLRoleRepository,
    SQLUserRepository,
)

AUTH = "/api/v1/auth"
EVENTS = "/api/v1/activity/events"
DASHBOARDS = "/api/v1/dashboards"
PASSWORD = "SecurePass1!"
NOW = datetime.now(UTC)


async def _token(client: AsyncClient, db: AsyncSession, role: RoleName) -> tuple[str, str]:
    name = f"dash_{role.value.lower()}"
    r = await client.post(
        f"{AUTH}/register",
        json={
            "username": name,
            "email": f"{name}@example.com",
            "password": PASSWORD,
            "full_name": name,
        },
    )
    assert r.status_code == 201, r.text
    users, roles = SQLUserRepository(db), SQLRoleRepository(db)
    user = await users.get_by_email(f"{name}@example.com")
    user.set_roles([await roles.get_by_name(role)])
    await users.save(user)
    await db.commit()
    r = await client.post(
        f"{AUTH}/login", json={"email": f"{name}@example.com", "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"], str(user.id)


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _event(minutes_ago: float, **extra) -> dict:
    when = NOW - timedelta(minutes=minutes_ago)
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "app_launch",
        "timestamp": when.isoformat().replace("+00:00", "Z"),
        "user_id": "VISHWA\\vishw",
        "device_id": "WS-1",
        "source_dataset": "win_endpoint",
        "target_resource": "notepad.exe",
        "risk_indicators": [],
        "tags": ["win_endpoint"],
        "raw_payload": {"secret": "not for the API"},
        "ingested_at": NOW.isoformat(),
        **extra,
    }


def _alert(severity: str, status: str = "OPEN", hours_ago: float = 1, **extra) -> dict:
    return {
        "_id": str(uuid.uuid4()),
        "idempotency_key": str(uuid.uuid4()),
        "user_id": "insider.jane",
        "title": f"{severity} alert",
        "severity": severity,
        "status": status,
        "risk_score": 90.0,
        "created_at": NOW - timedelta(hours=hours_ago),
        "updated_at": NOW - timedelta(hours=hours_ago),
        **extra,
    }


def _result(
    user_id: str,
    days_ago: int,
    score: float,
    prediction: str = "anomaly",
    baseline: str = "personal",
) -> dict:
    return {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "window": "daily",
        "window_start": (NOW - timedelta(days=days_ago)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ),
        "prediction": prediction,
        "risk_score": score,
        "risk_level": "CRITICAL" if score >= 80 else "HIGH" if score >= 60 else "LOW",
        "baseline_source": baseline,
        "top_behavioral_deviations": [
            {
                "feature": "usb_activity_count",
                "value": 9.0,
                "baseline_mean": 0.5,
                "baseline_std": 1.0,
                "zscore": 8.5,
            }
        ],
        "created_at": NOW,
    }


# ─── Activity events ────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_require_authentication(async_client: AsyncClient):
    assert (await async_client.get(EVENTS)).status_code == 401
    assert (await async_client.get(f"{DASHBOARDS}/soc")).status_code == 401


@pytest.mark.asyncio
async def test_collected_events_are_browsable(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token, _ = await _token(async_client, db_session, RoleName.VIEWER)
    await mongo_mock_db["canonical_events"].insert_many(
        [
            _event(5),
            _event(30, event_type="usb_insert", risk_indicators=["usb_device_connected"]),
            _event(60 * 30, event_type="logon", user_id="insider.jane"),  # 30 hours ago
        ]
    )

    page = (await async_client.get(EVENTS, headers=_h(token))).json()
    assert page["total"] == 3
    assert [e["event_type"] for e in page["events"]] == ["app_launch", "usb_insert", "logon"]
    assert "raw_payload" not in page["events"][0]

    usb = (
        await async_client.get(EVENTS, params={"event_type": "usb_insert"}, headers=_h(token))
    ).json()
    assert usb["total"] == 1 and usb["events"][0]["risk_indicators"] == ["usb_device_connected"]

    since = (NOW - timedelta(hours=2)).isoformat()
    recent = (
        await async_client.get(EVENTS, params={"start": since, "limit": 1}, headers=_h(token))
    ).json()
    assert recent["total"] == 2 and len(recent["events"]) == 1

    summary = (await async_client.get(f"{EVENTS}/summary", headers=_h(token))).json()
    assert summary["total"] == 2, "the 30-hour-old logon is outside the window"
    assert summary["flagged"] == 1
    assert summary["by_event_type"] == {"app_launch": 1, "usb_insert": 1}
    assert len(summary["hourly"]) == 24 and sum(h["count"] for h in summary["hourly"]) == 2


# ─── Access ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_each_role_reaches_only_its_own_dashboard(
    async_client: AsyncClient, db_session: AsyncSession
):
    cases = {
        RoleName.SECURITY_ANALYST: "analyst",
        RoleName.SOC_ENGINEER: "soc",
        RoleName.SECURITY_MANAGER: "manager",
    }
    for role, own in cases.items():
        token, _ = await _token(async_client, db_session, role)
        for dashboard in cases.values():
            r = await async_client.get(f"{DASHBOARDS}/{dashboard}", headers=_h(token))
            expected = 200 if dashboard == own else 403
            assert r.status_code == expected, (role, dashboard, r.text)


# ─── Figures ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyst_dashboard(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token, analyst_id = await _token(async_client, db_session, RoleName.SECURITY_ANALYST)
    await mongo_mock_db["alerts"].insert_many(
        [
            _alert("CRITICAL"),
            _alert("HIGH", status="ACKNOWLEDGED"),
            _alert("HIGH", status="RESOLVED"),
            _alert("MEDIUM", status="FALSE_POSITIVE"),
            _alert("LOW", hours_ago=48),
        ]
    )
    await mongo_mock_db["investigations"].insert_many(
        [
            {
                "_id": "inv-mine",
                "title": "USB exfil",
                "severity": "HIGH",
                "status": "IN_PROGRESS",
                "assigned_to": analyst_id,
                "related_user_ids": ["insider.jane"],
                "created_at": NOW,
                "updated_at": NOW,
            },
            {
                "_id": "inv-free",
                "title": "Odd logons",
                "severity": "CRITICAL",
                "status": "OPEN",
                "assigned_to": None,
                "related_user_ids": [],
                "created_at": NOW,
                "updated_at": NOW,
            },
            {
                "_id": "inv-done",
                "title": "Closed case",
                "severity": "LOW",
                "status": "CLOSED",
                "resolution": "Authorised backup",
                "related_user_ids": ["bob"],
                "created_at": NOW - timedelta(days=3),
                "updated_at": NOW,
                "closed_at": NOW,
            },
        ]
    )
    await mongo_mock_db["anomaly_results"].insert_many(
        [
            _result("insider.jane", 1, 92.0),
            _result("insider.jane", 0, 70.0),
            _result("new.starter", 0, 45.0, baseline="global"),
        ]
    )

    body = (await async_client.get(f"{DASHBOARDS}/analyst", headers=_h(token))).json()

    alerts = body["threat_alerts"]
    assert alerts["open_total"] == 3
    assert alerts["open_by_severity"] == {"LOW": 1, "MEDIUM": 0, "HIGH": 1, "CRITICAL": 1}
    assert alerts["new_last_24h"] == 4
    assert alerts["recent"][0]["severity"] == "CRITICAL"

    [jane, starter] = body["insider_risk"]["users"]
    assert (jane["user_id"], jane["max_risk_score"], jane["latest_risk_score"]) == (
        "insider.jane",
        92.0,
        70.0,
    )
    assert jane["anomalies"] == 2 and starter["baseline_source"] == "global"

    queue = body["investigation_queue"]
    assert [i["id"] for i in queue["assigned_to_me"]] == ["inv-mine"]
    assert [i["id"] for i in queue["unassigned"]] == ["inv-free"]
    assert queue["counts_by_status"] == {"OPEN": 1, "IN_PROGRESS": 1, "RESOLVED": 0, "CLOSED": 1}

    incidents = body["incident_summaries"]
    assert (incidents["resolved"], incidents["false_positives"]) == (1, 1)
    assert incidents["recent"][0]["resolution"] == "Authorised backup"


@pytest.mark.asyncio
async def test_soc_dashboard(async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db):
    token, _ = await _token(async_client, db_session, RoleName.SOC_ENGINEER)
    await mongo_mock_db["canonical_events"].insert_many(
        [
            _event(10, event_type="file_download", risk_indicators=["executable_downloaded"]),
            _event(20, event_type="file_copy", risk_indicators=["file_copied_to_removable_media"]),
            _event(25, event_type="file_copy", risk_indicators=["file_copied_to_removable_media"]),
            _event(
                15,
                event_type="network_connection",
                target_resource="93.184.216.34:443",
                enrichments={"remote_scope": "public", "remote_address": "93.184.216.34"},
            ),
            _event(
                16,
                event_type="network_connection",
                user_id="bob",
                enrichments={"remote_scope": "public", "remote_address": "93.184.216.34"},
            ),
            _event(
                17,
                event_type="network_connection",
                enrichments={"remote_scope": "private", "remote_address": "192.168.1.5"},
            ),
        ]
    )
    await mongo_mock_db["anomaly_results"].insert_many(
        [
            _result("insider.jane", 0, 85.0),
            _result("bob", 0, 20.0, prediction="normal"),
        ]
    )

    body = (await async_client.get(f"{DASHBOARDS}/soc", headers=_h(token))).json()

    events = body["security_events"]
    assert events["total"] == 6 and events["flagged"] == 3 and len(events["recent"]) == 6

    anomalies = body["behavioral_anomalies"]
    assert (anomalies["results"], anomalies["anomalies"]) == (2, 1)
    assert anomalies["recent"][0]["top_deviation"] == "usb_activity_count (z=+8.5)"

    intel = body["threat_intelligence"]
    assert "No external threat-intelligence feed" in intel["note"]
    assert intel["indicators"][0] == {
        "indicator": "file_copied_to_removable_media",
        "count": 2,
        "last_seen": intel["indicators"][0]["last_seen"],
    }
    assert intel["external_destinations"] == [
        {"destination": "93.184.216.34", "count": 2, "users": 2}
    ]
    assert set(intel["pipeline"]) == {
        "scheduler_enabled",
        "running",
        "last_success_at",
        "next_run_at",
        "last_error",
    }


@pytest.mark.asyncio
async def test_manager_dashboard(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token, _ = await _token(async_client, db_session, RoleName.SECURITY_MANAGER)
    await mongo_mock_db["alerts"].insert_many(
        [
            # Acknowledged after 2 hours: within the 24-hour critical SLA.
            _alert(
                "CRITICAL",
                status="ACKNOWLEDGED",
                hours_ago=50,
                acknowledged_at=NOW - timedelta(hours=48),
            ),
            # Never acknowledged and past its deadline: a breach.
            _alert("CRITICAL", hours_ago=30),
            # Too new to judge.
            _alert("CRITICAL", hours_ago=1),
            _alert(
                "HIGH",
                status="RESOLVED",
                hours_ago=10,
                acknowledged_at=NOW - timedelta(hours=9),
                resolved_at=NOW - timedelta(hours=6),
            ),
        ]
    )
    await mongo_mock_db["anomaly_results"].insert_many(
        [
            _result("insider.jane", 2, 88.0),
            _result("insider.jane", 0, 64.0),
            _result("bob", 0, 12.0, prediction="normal", baseline="global"),
        ]
    )

    body = (await async_client.get(f"{DASHBOARDS}/manager", headers=_h(token))).json()

    posture = body["risk_posture"]
    assert posture["monitored_users"] == 2
    assert posture["high_risk_users"] == 1
    assert posture["org_risk_index"] == 38.0
    assert posture["open_critical_alerts"] == 3

    series = body["risk_trends"]["series"]
    assert len(series) == 30 and series[-1]["date"] == NOW.date().isoformat()
    assert series[-1]["max_risk_score"] == 64.0 and series[-1]["anomalies"] == 1
    assert sum(day["alerts_created"] for day in series) == 4

    report = body["insider_threat_report"]
    assert report["top_users"][0]["user_id"] == "insider.jane"
    assert report["alerts_by_severity"]["CRITICAL"] == 3

    compliance = body["compliance"]
    assert compliance["alerts_total"] == 4
    assert compliance["triaged_pct"] == 50.0
    assert compliance["critical_within_sla_pct"] == 50.0
    assert compliance["mean_hours_to_acknowledge"] == 1.5
    assert compliance["mean_hours_to_resolve"] == 4.0
    assert compliance["devices_enrolled"] == 0 and compliance["agent_coverage_pct"] is None


@pytest.mark.asyncio
async def test_manager_dashboard_uses_weighted_risk_scores_when_available(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    from app.modules.detection.domain.categories import AnomalyCategory
    from app.modules.detection.domain.finding import Finding
    from app.modules.risk.application.scoring import score_employee, signals_from_findings
    from app.modules.risk.infrastructure.mongo_risk_store import MongoRiskScoreStore

    token, _ = await _token(async_client, db_session, RoleName.SECURITY_MANAGER)
    today = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    leak = Finding(
        user_id="insider.jane",
        day=today,
        category=AnomalyCategory.ABNORMAL_DATA_DOWNLOAD,
        detector="abnormal_data_download",
        severity=80,
        title="Leak",
        description="d",
    )
    scores = [
        score_employee("insider.jane", today - timedelta(days=1), []),
        score_employee("insider.jane", today, signals_from_findings([leak])),
        score_employee("bob", today, []),
    ]
    await MongoRiskScoreStore(mongo_mock_db).upsert_many(scores)
    # Model results are ignored once weighted scores exist.
    await mongo_mock_db["anomaly_results"].insert_one(_result("someone.else", 0, 99.0))

    body = (await async_client.get(f"{DASHBOARDS}/manager", headers=_h(token))).json()

    posture = body["risk_posture"]
    assert posture["risk_source"] == "weighted_risk"
    assert posture["monitored_users"] == 2
    assert posture["high_risk_users"] == 1  # jane's priority today is 64
    assert posture["org_risk_index"] == 8.0  # (16 + 0) / 2
    series = body["risk_trends"]["series"]
    assert series[-1]["max_risk_score"] == 16.0 and series[-1]["anomalies"] == 1
    [top, *_] = body["insider_threat_report"]["top_users"]
    assert top["user_id"] == "insider.jane" and top["max_priority"] == 64.0
