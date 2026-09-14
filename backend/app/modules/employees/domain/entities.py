"""
ITBIS — Employees Module: the employee directory (domain)

Monitoring sees accounts (`VISHWA\\vishw`, `ACM2278`, `jane@corp.example`);
people are employees. The directory links them: each employee has an ID,
department, role and manager, and owns one or more accounts and devices.

Events are stamped with the employee behind their account when ingested, and
detection learns who is privileged and who owns which machine from here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EmployeeStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"


class AccountType(str, Enum):
    WINDOWS = "windows"
    EMAIL = "email"
    DATASET = "dataset"  # an identifier from an imported dataset, e.g. CERT's user id
    OTHER = "other"


def account_key(account: str) -> str:
    """Accounts match case-insensitively (Windows and email both ignore case)."""
    return account.strip().lower()


@dataclass
class EmployeeAccount:
    account: str
    account_type: AccountType = AccountType.WINDOWS
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)

    @property
    def key(self) -> str:
        return account_key(self.account)


@dataclass
class EmployeeDevice:
    device_id: str
    #: A machine assigned to this person (as opposed to one they merely use).
    dedicated: bool = True
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class Employee:
    employee_id: str
    full_name: str
    email: str | None = None
    department: str = ""
    job_title: str = ""
    team: str = ""
    manager_employee_id: str | None = None
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    #: Holds administrative rights (e.g. IT administrators).
    privileged: bool = False
    accounts: list[EmployeeAccount] = field(default_factory=list)
    devices: list[EmployeeDevice] = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def primary_account(self) -> str | None:
        """The account events are most likely attributed to."""
        order = {AccountType.WINDOWS: 0, AccountType.DATASET: 1, AccountType.EMAIL: 2}
        ranked = sorted(self.accounts, key=lambda a: order.get(a.account_type, 3))
        return ranked[0].account if ranked else None


@dataclass(frozen=True)
class EmployeeRef:
    """What ingestion stamps on an event."""

    employee_id: str
    full_name: str
    department: str
