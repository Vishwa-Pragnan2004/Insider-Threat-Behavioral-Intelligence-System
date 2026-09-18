"""
ITBIS — Feedback Module: SQLAlchemy models
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Float, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.base_model import Base


class AnalystVerdictModel(Base):
    """One recorded analyst judgement of one alert.

    There is no unique index on `alert_id`: an alert can be judged more
    than once over its life.  At most one row per alert has
    `superseded_at IS NULL`, which the service maintains.
    """

    __tablename__ = "analyst_verdicts"
    # One verdict in force per alert. Expressed as a partial unique index so
    # superseded rows accumulate freely. SQLite (tests) honours the same
    # `sqlite_where` form, so the rule is enforced in both.
    __table_args__ = (
        Index(
            "uq_analyst_verdicts_current_per_alert",
            "alert_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
            sqlite_where=text("superseded_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)

    subject_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    subject_day: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    verdict: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ─── Evidence snapshot (what the system believed at the time) ──────
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    priority: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSONB on Postgres, plain JSON on SQLite (tests).
    detectors: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )
    categories: Mapped[list[Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )

    # ─── Supersession ─────────────────────────────────────────────────
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
