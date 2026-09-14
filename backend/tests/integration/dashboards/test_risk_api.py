"""
ITBIS — Integration tests: detection findings and insider risk API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.detection.domain.categories import AnomalyCategory
from app.modules.detection.domain.finding import Finding
from app.modules.detection.infrastructure.mongo_finding_store import MongoFindingStore
from app.modules.identity.domain.enums import RoleName
from app.modules.risk.application.scoring import score_employee, signals_from_findings
from app.modules.risk.infrastructure.mongo_risk_store import MongoRiskScoreStore
from tests.integration.dashboards.test_dashboards_api import _h, _token

TODAY = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _finding(user: str, category: AnomalyCategory, severity: float, days_ago: int = 0):
    return Finding(
        user_id=user,
        day=TODAY - timedelta(days=days_ago),
        category=category,
        detector=category.value.lower(),
        severity=severity,
        title=category.value.title(),
        description=f"{user} did something",
        evidence={"example": True},
    )


async def _seed(db) -> None:
    jane = [
        _finding("jane", AnomalyCategory.ABNORMAL_DATA_DOWNLOAD, 80),
        _finding("jane", AnomalyCategory.UNUSUAL_LOGIN_TIME, 65, days_ago=1),
    ]
    bob = [_finding("bob", AnomalyCategory.INSIDER_RISK_INDICATOR, 40)]
    findings = MongoFindingStore(db)
    await findings.replace_for_user_days(
        "jane", TODAY - timedelta(days=2), TODAY + timedelta(days=1), jane
    )
    await findings.replace_for_user_days("bob", TODAY, TODAY + timedelta(days=1), bob)

    scores = []
    for user, user_findings in (("jane", jane), ("bob", bob)):
        signals = signals_from_findings(user_findings)
        for days_ago in (1, 0):
            scores.append(score_employee(user, TODAY - timedelta(days=days_ago), signals))
    await MongoRiskScoreStore(db).upsert_many(scores)


@pytest.mark.asyncio
async def test_risk_endpoints_require_authentication(async_client: AsyncClient):
    for path in ("/api/v1/risk/employees", "/api/v1/detections/findings", "/api/v1/risk/model"):
        assert (await async_client.get(path)).status_code == 401


@pytest.mark.asyncio
async def test_categories_and_model(async_client: AsyncClient, db_session: AsyncSession):
    token, _ = await _token(async_client, db_session, RoleName.VIEWER)

    categories = (await async_client.get("/api/v1/detections/categories", headers=_h(token))).json()
    model = (await async_client.get("/api/v1/risk/model", headers=_h(token))).json()

    by_name = {c["category"]: c for c in categories}
    assert by_name["EXCESSIVE_FILE_TRANSFER"]["engine"] == "data_exfiltration"
    assert by_name["PRIVILEGE_ABUSE"]["risk_component"] == "privilege_misuse"
    weights = {c["component"]: c["weight"] for c in model["components"]}
    assert weights["behavioral_anomalies"] == 0.35 and sum(weights.values()) == pytest.approx(1)
    assert [b["level"] for b in model["bands"]] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@pytest.mark.asyncio
async def test_findings_filters(async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db):
    token, _ = await _token(async_client, db_session, RoleName.VIEWER)
    await _seed(mongo_mock_db)
    url = "/api/v1/detections/findings"

    everything = (await async_client.get(url, headers=_h(token))).json()
    janes = (await async_client.get(url, params={"user_id": "jane"}, headers=_h(token))).json()
    severe = (await async_client.get(url, params={"min_severity": 60}, headers=_h(token))).json()
    exfil = (
        await async_client.get(url, params={"engine": "data_exfiltration"}, headers=_h(token))
    ).json()

    assert everything["total"] == 3
    assert janes["total"] == 2 and janes["findings"][0]["severity"] == 80.0
    assert {f["category"] for f in severe["findings"]} == {
        "ABNORMAL_DATA_DOWNLOAD",
        "UNUSUAL_LOGIN_TIME",
    }
    [only] = exfil["findings"]
    assert only["category_label"] == "Abnormal data download / upload"
    assert only["evidence"] == {"example": True}


@pytest.mark.asyncio
async def test_employees_are_ranked_by_priority(
    async_client: AsyncClient, db_session: AsyncSession, mongo_mock_db
):
    token, _ = await _token(async_client, db_session, RoleName.VIEWER)
    await _seed(mongo_mock_db)

    ranked = (await async_client.get("/api/v1/risk/employees", headers=_h(token))).json()
    detail = (await async_client.get("/api/v1/risk/employees/jane", headers=_h(token))).json()

    assert [e["user_id"] for e in ranked["employees"]] == ["jane", "bob"]
    jane = ranked["employees"][0]
    assert jane["day"].startswith(TODAY.date().isoformat())
    assert jane["priority"] == 64.0 and jane["dominant_component"] == "data_access_violations"
    assert set(jane["components"]) == {
        "behavioral_anomalies",
        "privilege_misuse",
        "data_access_violations",
        "access_pattern_deviations",
        "historical_security_events",
    }
    assert len(detail["series"]) == 2 and detail["latest"]["score"] == jane["score"]
    assert len(detail["findings"]) == 2

    filtered = (
        await async_client.get(
            "/api/v1/risk/employees", params={"min_priority": 60}, headers=_h(token)
        )
    ).json()
    assert [e["user_id"] for e in filtered["employees"]] == ["jane"]
