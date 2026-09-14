"""
ITBIS — Insider risk and detection findings API

    GET /api/v1/detections/categories            anomaly categories and their engines
    GET /api/v1/detections/findings              detector findings (filterable)
    GET /api/v1/risk/model                       weights and risk bands
    GET /api/v1/risk/employees                   latest risk per employee, by priority
    GET /api/v1/risk/employees/{user_id}         one employee: daily scores and findings

All endpoints need anomaly:read.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.mongo_client import get_mongo_db
from app.modules.detection.domain.categories import (
    CATEGORY_ENGINE,
    CATEGORY_LABELS,
    AnomalyCategory,
    DetectionEngine,
)
from app.modules.detection.domain.finding import Finding
from app.modules.detection.infrastructure.mongo_finding_store import MongoFindingStore
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import require_permission
from app.modules.risk.domain.model import (
    CATEGORY_COMPONENT,
    COMPONENT_LABELS,
    RISK_MODEL_VERSION,
    RISK_WEIGHTS,
    EmployeeRiskScore,
)
from app.modules.risk.infrastructure.mongo_risk_store import MongoRiskScoreStore

READ = [Depends(require_permission(PermissionName.ANOMALY_READ))]

detections_router = APIRouter()
risk_router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────


class CategoryOut(BaseModel):
    category: str
    label: str
    engine: str
    risk_component: str


class FindingOut(BaseModel):
    id: str
    user_id: str
    day: datetime
    category: str
    category_label: str
    engine: str
    detector: str
    severity: float
    title: str
    description: str
    evidence: dict[str, Any]
    event_ids: list[str]
    detector_version: str

    @classmethod
    def from_finding(cls, f: Finding) -> FindingOut:
        return cls(
            id=str(f.id),
            user_id=f.user_id,
            day=f.day,
            category=f.category.value,
            category_label=CATEGORY_LABELS[f.category],
            engine=f.engine.value,
            detector=f.detector,
            severity=f.severity,
            title=f.title,
            description=f.description,
            evidence=f.evidence,
            event_ids=f.event_ids,
            detector_version=f.detector_version,
        )


class FindingListOut(BaseModel):
    findings: list[FindingOut]
    total: int
    skip: int
    limit: int


class RiskComponentOut(BaseModel):
    component: str
    label: str
    weight: float


class RiskBandOut(BaseModel):
    level: str
    min_score: float
    max_score: float


class RiskModelOut(BaseModel):
    version: str
    components: list[RiskComponentOut]
    bands: list[RiskBandOut]
    alert_min_priority: float


class EmployeeRiskOut(BaseModel):
    user_id: str
    day: datetime
    score: float
    level: str
    priority: float
    trend: float | None
    dominant_component: str | None
    components: dict[str, float]
    top_signals: list[dict[str, Any]]

    @classmethod
    def from_score(cls, s: EmployeeRiskScore) -> EmployeeRiskOut:
        return cls(
            user_id=s.user_id,
            day=s.day,
            score=s.score,
            level=s.level.value,
            priority=s.priority,
            trend=s.trend,
            dominant_component=s.dominant_component.value if s.dominant_component else None,
            components={c.value: v for c, v in s.components.items()},
            top_signals=s.top_signals,
        )


class EmployeeRiskListOut(BaseModel):
    since: datetime
    employees: list[EmployeeRiskOut]


class EmployeeRiskDetailOut(BaseModel):
    user_id: str
    latest: EmployeeRiskOut | None
    series: list[EmployeeRiskOut]
    findings: list[FindingOut]


def _today() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


# ─── Detections ─────────────────────────────────────────────


@detections_router.get(
    "/categories", response_model=list[CategoryOut], summary="Anomaly categories", dependencies=READ
)
async def list_categories() -> list[CategoryOut]:
    return [
        CategoryOut(
            category=c.value,
            label=CATEGORY_LABELS[c],
            engine=CATEGORY_ENGINE[c].value,
            risk_component=CATEGORY_COMPONENT[c].value,
        )
        for c in AnomalyCategory
    ]


@detections_router.get(
    "/findings", response_model=FindingListOut, summary="Detector findings", dependencies=READ
)
async def list_findings(
    user_id: str | None = Query(None, max_length=255),
    category: AnomalyCategory | None = None,
    engine: DetectionEngine | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    min_severity: float | None = Query(None, ge=0, le=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    mongo_db: Any = Depends(get_mongo_db),
) -> FindingListOut:
    findings, total = await MongoFindingStore(mongo_db).list_findings(
        user_id=user_id,
        start=start,
        end=end,
        category=category,
        engine=engine,
        min_severity=min_severity,
        skip=skip,
        limit=limit,
    )
    return FindingListOut(
        findings=[FindingOut.from_finding(f) for f in findings],
        total=total,
        skip=skip,
        limit=limit,
    )


# ─── Risk ───────────────────────────────────────────────────


@risk_router.get("/model", response_model=RiskModelOut, summary="Risk model", dependencies=READ)
async def risk_model() -> RiskModelOut:
    from app.modules.alerts.application.risk_alert_service import RiskAlertPolicy

    return RiskModelOut(
        version=RISK_MODEL_VERSION,
        components=[
            RiskComponentOut(component=c.value, label=COMPONENT_LABELS[c], weight=w)
            for c, w in RISK_WEIGHTS.items()
        ],
        bands=[
            RiskBandOut(level="LOW", min_score=0, max_score=39.9),
            RiskBandOut(level="MEDIUM", min_score=40, max_score=59.9),
            RiskBandOut(level="HIGH", min_score=60, max_score=79.9),
            RiskBandOut(level="CRITICAL", min_score=80, max_score=100),
        ],
        alert_min_priority=RiskAlertPolicy().min_priority,
    )


@risk_router.get(
    "/employees",
    response_model=EmployeeRiskListOut,
    summary="Latest insider risk per employee, highest priority first",
    dependencies=READ,
)
async def list_employee_risk(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
    min_priority: float | None = Query(None, ge=0, le=100),
    mongo_db: Any = Depends(get_mongo_db),
) -> EmployeeRiskListOut:
    since = _today() - timedelta(days=days - 1)
    scores = await MongoRiskScoreStore(mongo_db).latest_per_user(
        since=since, limit=limit, min_priority=min_priority
    )
    return EmployeeRiskListOut(
        since=since, employees=[EmployeeRiskOut.from_score(s) for s in scores]
    )


@risk_router.get(
    "/employees/{user_id}",
    response_model=EmployeeRiskDetailOut,
    summary="One employee's risk history and findings",
    dependencies=READ,
)
async def employee_risk_detail(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
    mongo_db: Any = Depends(get_mongo_db),
) -> EmployeeRiskDetailOut:
    end = _today() + timedelta(days=1)
    start = end - timedelta(days=days)
    series = await MongoRiskScoreStore(mongo_db).series(user_id, start, end)
    findings, _ = await MongoFindingStore(mongo_db).list_findings(
        user_id=user_id, start=start, end=end, limit=200
    )
    return EmployeeRiskDetailOut(
        user_id=user_id,
        latest=EmployeeRiskOut.from_score(series[-1]) if series else None,
        series=[EmployeeRiskOut.from_score(s) for s in series],
        findings=[FindingOut.from_finding(f) for f in findings],
    )
