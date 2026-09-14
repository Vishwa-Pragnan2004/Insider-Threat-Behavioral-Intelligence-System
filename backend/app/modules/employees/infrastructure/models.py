"""
ITBIS — Employees Module: SQLAlchemy models
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.infrastructure.base_model import Base


class EmployeeModel(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    team: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    manager_employee_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    privileged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    accounts: Mapped[list[EmployeeAccountModel]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", lazy="selectin"
    )
    devices: Mapped[list[EmployeeDeviceModel]] = relationship(
        back_populates="employee", cascade="all, delete-orphan", lazy="selectin"
    )


class EmployeeAccountModel(Base):
    __tablename__ = "employee_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    account: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Lower-cased account; one account belongs to at most one employee.
    account_key: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    employee: Mapped[EmployeeModel] = relationship(back_populates="accounts")


class EmployeeDeviceModel(Base):
    __tablename__ = "employee_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    dedicated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    employee: Mapped[EmployeeModel] = relationship(back_populates="devices")
