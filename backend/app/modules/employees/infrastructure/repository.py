"""
ITBIS — Employees Module: SQL repository
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.employees.domain.entities import (
    AccountType,
    Employee,
    EmployeeAccount,
    EmployeeDevice,
    EmployeeRef,
    EmployeeStatus,
    account_key,
)
from app.modules.employees.infrastructure.models import (
    EmployeeAccountModel,
    EmployeeDeviceModel,
    EmployeeModel,
)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _to_domain(m: EmployeeModel) -> Employee:
    return Employee(
        id=m.id,
        employee_id=m.employee_id,
        full_name=m.full_name,
        email=m.email,
        department=m.department,
        job_title=m.job_title,
        team=m.team,
        manager_employee_id=m.manager_employee_id,
        status=EmployeeStatus(m.status),
        privileged=m.privileged,
        accounts=[
            EmployeeAccount(
                id=a.id,
                account=a.account,
                account_type=AccountType(a.account_type),
                created_at=_as_utc(a.created_at),
            )
            for a in sorted(m.accounts, key=lambda a: a.created_at)
        ],
        devices=[
            EmployeeDevice(
                id=d.id,
                device_id=d.device_id,
                dedicated=d.dedicated,
                created_at=_as_utc(d.created_at),
            )
            for d in sorted(m.devices, key=lambda d: d.created_at)
        ],
        created_at=_as_utc(m.created_at),
        updated_at=_as_utc(m.updated_at),
    )


class SQLEmployeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _model(self, employee_id: str) -> EmployeeModel | None:
        result = await self._session.execute(
            select(EmployeeModel).where(EmployeeModel.employee_id == employee_id)
        )
        return result.scalars().first()

    async def get(self, employee_id: str) -> Employee | None:
        model = await self._model(employee_id)
        return _to_domain(model) if model else None

    async def list(
        self,
        *,
        search: str | None = None,
        department: str | None = None,
        status: EmployeeStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Employee], int]:
        stmt = select(EmployeeModel)
        if search:
            like = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(EmployeeModel.employee_id).like(like),
                    func.lower(EmployeeModel.full_name).like(like),
                    func.lower(func.coalesce(EmployeeModel.email, "")).like(like),
                )
            )
        if department:
            stmt = stmt.where(EmployeeModel.department == department)
        if status:
            stmt = stmt.where(EmployeeModel.status == status.value)
        total = (
            await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar_one()
        rows = await self._session.execute(
            stmt.order_by(EmployeeModel.full_name).offset(skip).limit(limit)
        )
        return [_to_domain(m) for m in rows.scalars().all()], int(total)

    async def save(self, employee: Employee) -> Employee:
        """Insert or update the employee's own fields (accounts/devices are managed separately)."""
        model = await self._model(employee.employee_id)
        now = datetime.now(UTC)
        if model is None:
            model = EmployeeModel(id=employee.id, employee_id=employee.employee_id, created_at=now)
            self._session.add(model)
        for name in (
            "full_name",
            "email",
            "department",
            "job_title",
            "team",
            "manager_employee_id",
            "privileged",
        ):
            setattr(model, name, getattr(employee, name))
        model.status = employee.status.value
        model.updated_at = now
        await self._session.flush()
        await self._session.refresh(model, attribute_names=["accounts", "devices"])
        return _to_domain(model)

    async def account_owner(self, account: str) -> str | None:
        """employee_id already holding `account`, if any."""
        result = await self._session.execute(
            select(EmployeeModel.employee_id)
            .join(EmployeeAccountModel, EmployeeAccountModel.employee_uuid == EmployeeModel.id)
            .where(EmployeeAccountModel.account_key == account_key(account))
        )
        return result.scalars().first()

    async def device_owner(self, device_id: str) -> str | None:
        result = await self._session.execute(
            select(EmployeeModel.employee_id)
            .join(EmployeeDeviceModel, EmployeeDeviceModel.employee_uuid == EmployeeModel.id)
            .where(EmployeeDeviceModel.device_id == device_id)
        )
        return result.scalars().first()

    async def add_account(self, employee_id: str, account: EmployeeAccount) -> None:
        model = await self._model(employee_id)
        assert model is not None
        # Through the collection, so the loaded employee stays in step.
        model.accounts.append(
            EmployeeAccountModel(
                id=account.id,
                employee_uuid=model.id,
                account=account.account.strip(),
                account_key=account.key,
                account_type=account.account_type.value,
                created_at=account.created_at,
            )
        )
        await self._session.flush()

    async def remove_account(self, employee_id: str, account_id: uuid.UUID) -> bool:
        model = await self._model(employee_id)
        target = next((a for a in (model.accounts if model else []) if a.id == account_id), None)
        if target is None:
            return False
        model.accounts.remove(target)  # delete-orphan removes the row
        await self._session.flush()
        return True

    async def add_device(self, employee_id: str, device: EmployeeDevice) -> None:
        model = await self._model(employee_id)
        assert model is not None
        model.devices.append(
            EmployeeDeviceModel(
                id=device.id,
                employee_uuid=model.id,
                device_id=device.device_id.strip(),
                dedicated=device.dedicated,
                created_at=device.created_at,
            )
        )
        await self._session.flush()

    async def remove_device(self, employee_id: str, device_uuid: uuid.UUID) -> bool:
        model = await self._model(employee_id)
        target = next((d for d in (model.devices if model else []) if d.id == device_uuid), None)
        if target is None:
            return False
        model.devices.remove(target)
        await self._session.flush()
        return True

    async def resolve_accounts(self, accounts: Iterable[str]) -> dict[str, EmployeeRef]:
        """{account_key: employee} for the accounts that are linked to someone."""
        keys = {account_key(a) for a in accounts if a}
        if not keys:
            return {}
        rows = await self._session.execute(
            select(
                EmployeeAccountModel.account_key,
                EmployeeModel.employee_id,
                EmployeeModel.full_name,
                EmployeeModel.department,
            )
            .join(EmployeeModel, EmployeeModel.id == EmployeeAccountModel.employee_uuid)
            .where(EmployeeAccountModel.account_key.in_(keys))
        )
        return {
            key: EmployeeRef(employee_id=eid, full_name=name, department=dept or "")
            for key, eid, name, dept in rows.all()
        }

    async def all_account_keys(self) -> set[str]:
        rows = await self._session.execute(select(EmployeeAccountModel.account_key))
        return set(rows.scalars().all())

    async def detection_facts(self) -> tuple[dict[str, str], set[str]]:
        """({dedicated device: owner's primary account}, {accounts of privileged employees})."""
        rows = await self._session.execute(select(EmployeeModel))
        owners: dict[str, str] = {}
        privileged: set[str] = set()
        for employee in (_to_domain(m) for m in rows.scalars().all()):
            primary = employee.primary_account()
            if primary:
                for device in employee.devices:
                    if device.dedicated:
                        owners[device.device_id] = primary
            if employee.privileged:
                privileged.update(a.account for a in employee.accounts)
        return owners, privileged
