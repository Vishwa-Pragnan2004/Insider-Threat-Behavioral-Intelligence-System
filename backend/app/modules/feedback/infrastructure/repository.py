"""
ITBIS — Feedback Module: SQL verdict repository
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.feedback.domain.entities import AnalystVerdict, EvidenceSnapshot
from app.modules.feedback.domain.enums import Verdict
from app.modules.feedback.domain.repositories import IVerdictRepository
from app.modules.feedback.infrastructure.models import AnalystVerdictModel


def _to_entity(row: AnalystVerdictModel) -> AnalystVerdict:
    return AnalystVerdict(
        id=row.id,
        alert_id=row.alert_id,
        subject_user_id=row.subject_user_id,
        subject_day=row.subject_day,
        verdict=Verdict(row.verdict),
        rationale=row.rationale,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        evidence=EvidenceSnapshot(
            source=row.source,
            severity=row.severity,
            risk_score=row.risk_score,
            priority=row.priority,
            model_version=row.model_version,
            feature_version=row.feature_version,
            detectors=list(row.detectors or []),
            categories=list(row.categories or []),
        ),
        superseded_at=row.superseded_at,
        superseded_by=row.superseded_by,
    )


class SqlVerdictRepository(IVerdictRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, verdict: AnalystVerdict) -> AnalystVerdict:
        row = AnalystVerdictModel(
            id=verdict.id,
            alert_id=verdict.alert_id,
            subject_user_id=verdict.subject_user_id,
            subject_day=verdict.subject_day,
            verdict=verdict.verdict.value,
            rationale=verdict.rationale,
            decided_by=verdict.decided_by,
            decided_at=verdict.decided_at,
            source=verdict.evidence.source,
            severity=verdict.evidence.severity,
            risk_score=verdict.evidence.risk_score,
            priority=verdict.evidence.priority,
            model_version=verdict.evidence.model_version,
            feature_version=verdict.evidence.feature_version,
            detectors=list(verdict.evidence.detectors),
            categories=list(verdict.evidence.categories),
            superseded_at=verdict.superseded_at,
            superseded_by=verdict.superseded_by,
        )
        self.session.add(row)
        await self.session.flush()
        return _to_entity(row)

    async def update(self, verdict: AnalystVerdict) -> AnalystVerdict:
        row = await self.session.get(AnalystVerdictModel, verdict.id)
        if row is None:  # pragma: no cover — the service only updates what it read
            raise ValueError(f"Verdict {verdict.id} not found")
        row.superseded_at = verdict.superseded_at
        row.superseded_by = verdict.superseded_by
        await self.session.flush()
        return _to_entity(row)

    async def current_for_alert(self, alert_id: uuid.UUID) -> AnalystVerdict | None:
        stmt = select(AnalystVerdictModel).where(
            AnalystVerdictModel.alert_id == alert_id,
            AnalystVerdictModel.superseded_at.is_(None),
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return _to_entity(row) if row else None

    async def history_for_alert(self, alert_id: uuid.UUID) -> list[AnalystVerdict]:
        stmt = (
            select(AnalystVerdictModel)
            .where(AnalystVerdictModel.alert_id == alert_id)
            .order_by(AnalystVerdictModel.decided_at.asc())
        )
        return [_to_entity(r) for r in (await self.session.execute(stmt)).scalars().all()]

    async def current_for_alerts(
        self, alert_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, AnalystVerdict]:
        if not alert_ids:
            return {}
        stmt = select(AnalystVerdictModel).where(
            AnalystVerdictModel.alert_id.in_(alert_ids),
            AnalystVerdictModel.superseded_at.is_(None),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return {r.alert_id: _to_entity(r) for r in rows}

    async def list_current(
        self,
        *,
        since: date | None = None,
        until: date | None = None,
        subject_user_id: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[list[AnalystVerdict], int]:
        conditions = [AnalystVerdictModel.superseded_at.is_(None)]
        if since is not None:
            conditions.append(AnalystVerdictModel.subject_day >= since)
        if until is not None:
            conditions.append(AnalystVerdictModel.subject_day <= until)
        if subject_user_id is not None:
            conditions.append(AnalystVerdictModel.subject_user_id == subject_user_id)

        total = (
            await self.session.execute(
                select(func.count()).select_from(AnalystVerdictModel).where(*conditions)
            )
        ).scalar_one()

        stmt = (
            select(AnalystVerdictModel)
            .where(*conditions)
            .order_by(AnalystVerdictModel.decided_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows], int(total)
