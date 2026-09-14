"""
ITBIS — Employees Module: directory service

Managing the directory (employees, their accounts and devices), bulk import,
and the two things the rest of the platform asks of it:

  * `EmployeeResolver`: which employee is behind an account, for stamping
    events at ingestion. Answers are cached briefly, since every batch of
    agent events asks about the same handful of accounts.
  * `detection_context`: privileged accounts and machine owners, so live
    detection knows what the dataset replay learns from LDAP.

Imports accept the platform's own CSV layout or CERT's LDAP export as-is.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.modules.detection.application.detectors import DetectionContext
from app.modules.employees.domain.entities import (
    AccountType,
    Employee,
    EmployeeAccount,
    EmployeeDevice,
    EmployeeRef,
    EmployeeStatus,
    account_key,
)
from app.modules.employees.infrastructure.repository import SQLEmployeeRepository

#: CERT's system-administrator role.
PRIVILEGED_TITLES = frozenset({"itadmin", "it administrator", "system administrator"})


class DirectoryError(Exception):
    """Base class for refused directory changes."""


class EmployeeNotFoundError(DirectoryError):
    pass


class DuplicateEmployeeError(DirectoryError):
    pass


class AccountInUseError(DirectoryError):
    pass


class DeviceInUseError(DirectoryError):
    pass


class InvalidImportError(DirectoryError):
    pass


@dataclass
class ImportResult:
    format: str
    created: int = 0
    updated: int = 0
    accounts_linked: int = 0
    devices_linked: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class EmployeeDirectoryService:
    def __init__(self, repo: SQLEmployeeRepository) -> None:
        self._repo = repo

    # ─── Employees ─────────────────────────────────────────

    async def get(self, employee_id: str) -> Employee:
        employee = await self._repo.get(employee_id)
        if employee is None:
            raise EmployeeNotFoundError(f"Employee {employee_id} not found")
        return employee

    async def create(self, employee: Employee) -> Employee:
        if await self._repo.get(employee.employee_id):
            raise DuplicateEmployeeError(f"Employee ID {employee.employee_id} is already in use.")
        return await self._repo.save(employee)

    async def update(self, employee_id: str, changes: dict) -> Employee:
        employee = await self.get(employee_id)
        for name, value in changes.items():
            setattr(employee, name, EmployeeStatus(value) if name == "status" else value)
        return await self._repo.save(employee)

    # ─── Accounts and devices ──────────────────────────────

    async def link_account(
        self, employee_id: str, account: str, account_type: AccountType
    ) -> Employee:
        await self.get(employee_id)
        owner = await self._repo.account_owner(account)
        if owner and owner != employee_id:
            raise AccountInUseError(f"Account {account} already belongs to employee {owner}.")
        if owner != employee_id:
            await self._repo.add_account(employee_id, EmployeeAccount(account, account_type))
        return await self.get(employee_id)

    async def unlink_account(self, employee_id, account_id) -> Employee:  # noqa: ANN001
        if not await self._repo.remove_account(employee_id, account_id):
            raise EmployeeNotFoundError("That account isn't linked to this employee.")
        return await self.get(employee_id)

    async def assign_device(self, employee_id: str, device_id: str, dedicated: bool) -> Employee:
        await self.get(employee_id)
        owner = await self._repo.device_owner(device_id)
        if owner and owner != employee_id:
            raise DeviceInUseError(f"Device {device_id} is already assigned to employee {owner}.")
        if owner != employee_id:
            await self._repo.add_device(employee_id, EmployeeDevice(device_id, dedicated))
        return await self.get(employee_id)

    async def unassign_device(self, employee_id, device_uuid) -> Employee:  # noqa: ANN001
        if not await self._repo.remove_device(employee_id, device_uuid):
            raise EmployeeNotFoundError("That device isn't assigned to this employee.")
        return await self.get(employee_id)

    # ─── Import ────────────────────────────────────────────

    async def import_csv(self, content: bytes) -> ImportResult:
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        columns = {c.strip().lower() for c in (reader.fieldnames or [])}
        if {"user_id", "employee_name", "role"} <= columns:
            fmt, rows = "cert_ldap", [_from_cert_ldap(r) for r in reader]
        elif {"employee_id", "full_name"} <= columns:
            fmt, rows = "itbis", [_from_itbis(r) for r in reader]
        else:
            raise InvalidImportError(
                "Unrecognised columns. Expected employee_id, full_name[, email, department, "
                "job_title, team, manager_employee_id, status, privileged, accounts, devices] "
                "or a CERT LDAP export (employee_name, user_id, email, role, …)."
            )
        result = ImportResult(format=fmt)
        supervisors: dict[str, str] = {}
        by_name: dict[str, str] = {}
        for line, row in enumerate(rows, start=2):
            if row is None:
                result.skipped += 1
                continue
            employee, accounts, devices, supervisor = row
            try:
                existing = await self._repo.get(employee.employee_id)
                if existing:
                    employee.id = existing.id
                    result.updated += 1
                else:
                    result.created += 1
                await self._repo.save(employee)
                for account, account_type in accounts:
                    owner = await self._repo.account_owner(account)
                    if owner is None:
                        await self._repo.add_account(
                            employee.employee_id, EmployeeAccount(account, account_type)
                        )
                        result.accounts_linked += 1
                    elif owner != employee.employee_id:
                        result.errors.append(f"line {line}: account {account} belongs to {owner}")
                for device_id in devices:
                    owner = await self._repo.device_owner(device_id)
                    if owner is None:
                        await self._repo.add_device(employee.employee_id, EmployeeDevice(device_id))
                        result.devices_linked += 1
                    elif owner != employee.employee_id:
                        result.errors.append(f"line {line}: device {device_id} belongs to {owner}")
            except DirectoryError as exc:
                result.errors.append(f"line {line}: {exc}")
                continue
            by_name[employee.full_name.strip().lower()] = employee.employee_id
            if supervisor:
                supervisors[employee.employee_id] = supervisor

        # CERT names supervisors rather than giving their IDs.
        for employee_id, supervisor in supervisors.items():
            manager = by_name.get(supervisor.strip().lower())
            if manager and manager != employee_id:
                employee = await self._repo.get(employee_id)
                if employee and employee.manager_employee_id != manager:
                    employee.manager_employee_id = manager
                    await self._repo.save(employee)
        result.errors = result.errors[:50]
        return result


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").replace(",", ";").split(";") if v.strip()]


def _from_itbis(row: dict) -> tuple | None:
    row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    if not row.get("employee_id") or not row.get("full_name"):
        return None
    status = row.get("status", "").upper() or "ACTIVE"
    employee = Employee(
        employee_id=row["employee_id"],
        full_name=row["full_name"],
        email=row.get("email") or None,
        department=row.get("department", ""),
        job_title=row.get("job_title", ""),
        team=row.get("team", ""),
        manager_employee_id=row.get("manager_employee_id") or None,
        status=EmployeeStatus(status)
        if status in EmployeeStatus.__members__
        else EmployeeStatus.ACTIVE,
        privileged=row.get("privileged", "").lower() in {"true", "yes", "1", "y"},
    )
    accounts = [
        (a, AccountType.EMAIL if "@" in a else AccountType.WINDOWS)
        for a in _split(row.get("accounts"))
    ]
    if employee.email and all(account_key(a) != account_key(employee.email) for a, _ in accounts):
        accounts.append((employee.email, AccountType.EMAIL))
    return employee, accounts, _split(row.get("devices")), None


def _from_cert_ldap(row: dict) -> tuple | None:
    row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    if not row.get("user_id") or not row.get("employee_name"):
        return None
    employee = Employee(
        employee_id=row["user_id"],
        full_name=row["employee_name"],
        email=row.get("email") or None,
        department=row.get("department", ""),
        job_title=row.get("role", ""),
        team=row.get("team", ""),
        privileged=row.get("role", "").lower() in PRIVILEGED_TITLES,
    )
    accounts = [(row["user_id"], AccountType.DATASET)]
    if employee.email:
        accounts.append((employee.email, AccountType.EMAIL))
    return employee, accounts, [], row.get("supervisor") or None


# ─── Used by ingestion and detection ────────────────────────


class EmployeeResolver:
    """Which employee is behind an account; answers (including 'nobody') cached briefly."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, EmployeeRef | None]] = {}

    def forget(self) -> None:
        self._cache.clear()

    async def resolve(
        self, repo: SQLEmployeeRepository, accounts: Iterable[str]
    ) -> dict[str, EmployeeRef]:
        """{account as given: employee} for accounts linked to someone."""
        now = time.monotonic()
        wanted = {a for a in accounts if a}
        missing = [
            a
            for a in wanted
            if (hit := self._cache.get(account_key(a))) is None or now - hit[0] > self._ttl
        ]
        if missing:
            found = await repo.resolve_accounts(missing)
            for account in missing:
                key = account_key(account)
                self._cache[key] = (now, found.get(key))
        out = {}
        for account in wanted:
            ref = self._cache.get(account_key(account), (0, None))[1]
            if ref is not None:
                out[account] = ref
        return out


employee_resolver = EmployeeResolver()


def stamp_employee(doc: dict, refs: dict[str, EmployeeRef]) -> None:
    """Fill employee_id / department on a stored event from the directory."""
    ref = refs.get(doc.get("user_id") or "")
    if ref is None:
        return
    doc["employee_id"] = doc.get("employee_id") or ref.employee_id
    doc["department"] = doc.get("department") or ref.department or None


async def detection_context(repo: SQLEmployeeRepository) -> DetectionContext:
    owners, privileged = await repo.detection_facts()
    return DetectionContext(pc_owners=owners, privileged_users=frozenset(privileged))
