"""
ITBIS — SQLAlchemy Declarative Base
Shared by all ORM models across every module.
Import this Base — never create a second one.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Project-wide SQLAlchemy declarative base.

    All ORM models must inherit from this class so Alembic can
    discover them for autogenerate and so we use a single metadata object.
    """

    # ── Soft conventions ──────────────────────────────────────
    # Subclasses should define __tablename__ as a class attribute.
    # Subclasses should use Mapped[] type annotations for columns.

    type_annotation_map: dict[Any, Any] = {}
