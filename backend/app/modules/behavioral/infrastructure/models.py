"""
ITBIS — Behavioral Module: SQLAlchemy ORM Model
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.infrastructure.base_model import Base


class BehavioralBaselineModel(Base):
    __tablename__ = "behavioral_baselines"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "feature_version", name="uq_behavioral_baseline_user_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    feature_version: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    # Use JSONB on Postgres, plain JSON on SQLite (tests).
    from sqlalchemy import JSON

    stats: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    observation_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_dataset: Mapped[str] = mapped_column(
        String(64), nullable=False, default="all"
    )
