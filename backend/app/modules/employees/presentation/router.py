"""
ITBIS — Employee directory API

    GET    /api/v1/employees                         list / search          employees:read
    GET    /api/v1/employees/unmapped-accounts       accounts seen in activity
                                                     but linked to nobody   employees:read
    POST   /api/v1/employees/import                  CSV (ITBIS or CERT LDAP) employees:manage
    POST   /api/v1/employees                         create                 employees:manage
    GET    /api/v1/employees/{employee_id}           one employee           employees:read
    PATCH  /api/v1/employees/{employee_id}           update                 employees:manage
    POST   /api/v1/employees/{employee_id}/accounts  link an account        employees:manage
    DELETE /api/v1/employees/{employee_id}/accounts/{account_id}            employees:manage
    POST   /api/v1/employees/{employee_id}/devices   assign a device        employees:manage
    DELETE /api/v1/employees/{employee_id}/devices/{device_uuid}            employees:manage
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.mongo_client import get_mongo_db
from app.modules.activity.application.event_queries import timestamp_bound
from app.modules.employees.application.directory_service import (
    AccountInUseError,
    DeviceInUseError,
    DirectoryError,
    DuplicateEmployeeError,
    EmployeeDirectoryService,
    EmployeeNotFoundError,
    InvalidImportError,
    employee_resolver,
)
from app.modules.employees.domain.entities import (
    AccountType,
    Employee,
    EmployeeStatus,
    account_key,
)
from app.modules.employees.infrastructure.repository import SQLEmployeeRepository
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.dependencies import require_permission

router = APIRouter()
READ = [Depends(require_permission(PermissionName.EMPLOYEES_READ))]
MANAGE = [Depends(require_permission(PermissionName.EMPLOYEES_MANAGE))]

#: Account names that are machines or the operating system, never a person.
NON_PERSON_ACCOUNTS = ("unknown", "system", "nt authority\\", "local service", "network service")


# ─── Schemas ────────────────────────────────────────────────


class AccountOut(BaseModel):
    id: str
    account: str
    account_type: str


class DeviceOut(BaseModel):
    id: str
    device_id: str
    dedicated: bool


class EmployeeOut(BaseModel):
    id: str
    employee_id: str
    full_name: str
    email: str | None
    department: str
    job_title: str
    team: str
    manager_employee_id: str | None
    status: str
    privileged: bool
    accounts: list[AccountOut]
    devices: list[DeviceOut]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_employee(cls, e: Employee) -> EmployeeOut:
        return cls(
            id=str(e.id),
            employee_id=e.employee_id,
            full_name=e.full_name,
            email=e.email,
            department=e.department,
            job_title=e.job_title,
            team=e.team,
            manager_employee_id=e.manager_employee_id,
            status=e.status.value,
            privileged=e.privileged,
            accounts=[
                AccountOut(id=str(a.id), account=a.account, account_type=a.account_type.value)
                for a in e.accounts
            ],
            devices=[
                DeviceOut(id=str(d.id), device_id=d.device_id, dedicated=d.dedicated)
                for d in e.devices
            ],
            created_at=e.created_at,
            updated_at=e.updated_at,
        )


class EmployeeListOut(BaseModel):
    employees: list[EmployeeOut]
    total: int
    skip: int
    limit: int


class EmployeeCreate(BaseModel):
    employee_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._@\\-]+$")
    full_name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr | None = None
    department: str = Field("", max_length=255)
    job_title: str = Field("", max_length=255)
    team: str = Field("", max_length=255)
    manager_employee_id: str | None = Field(None, max_length=64)
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    privileged: bool = False


class EmployeeUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    department: str | None = Field(None, max_length=255)
    job_title: str | None = Field(None, max_length=255)
    team: str | None = Field(None, max_length=255)
    manager_employee_id: str | None = Field(None, max_length=64)
    status: EmployeeStatus | None = None
    privileged: bool | None = None


class AccountLink(BaseModel):
    account: str = Field(..., min_length=1, max_length=255)
    account_type: AccountType = AccountType.WINDOWS


class DeviceAssign(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=255)
    dedicated: bool = True


class ImportOut(BaseModel):
    format: str
    created: int
    updated: int
    accounts_linked: int
    devices_linked: int
    skipped: int
    errors: list[str]


class UnmappedAccountOut(BaseModel):
    account: str
    events: int
    devices: list[str]
    last_seen: str | None


class UnmappedListOut(BaseModel):
    days: int
    accounts: list[UnmappedAccountOut]


# ─── Wiring ─────────────────────────────────────────────────


def _service(session: AsyncSession) -> EmployeeDirectoryService:
    return EmployeeDirectoryService(SQLEmployeeRepository(session))


async def _refused(session: AsyncSession, exc: DirectoryError) -> HTTPException:
    # Every refusal is decided before anything is written, so there is nothing
    # to roll back (and rolling back would discard the caller's other work).
    if isinstance(exc, EmployeeNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, DuplicateEmployeeError | AccountInUseError | DeviceInUseError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, InvalidImportError):
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        code = status.HTTP_400_BAD_REQUEST
    return HTTPException(status_code=code, detail=str(exc))


def _changed() -> None:
    # Account links drive event stamping; don't serve stale answers.
    employee_resolver.forget()


# ─── Reads ──────────────────────────────────────────────────


@router.get("", response_model=EmployeeListOut, summary="List employees", dependencies=READ)
async def list_employees(
    search: str | None = Query(None, max_length=100),
    department: str | None = Query(None, max_length=255),
    status_filter: EmployeeStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db),
) -> EmployeeListOut:
    employees, total = await SQLEmployeeRepository(session).list(
        search=search, department=department, status=status_filter, skip=skip, limit=limit
    )
    return EmployeeListOut(
        employees=[EmployeeOut.from_employee(e) for e in employees],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/unmapped-accounts",
    response_model=UnmappedListOut,
    summary="Accounts seen in activity that aren't linked to an employee",
    dependencies=READ,
)
async def unmapped_accounts(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
    mongo_db: Any = Depends(get_mongo_db),
) -> UnmappedListOut:
    linked = await SQLEmployeeRepository(session).all_account_keys()
    since = timestamp_bound(datetime.now(UTC) - timedelta(days=days))
    counts: Counter[str] = Counter()
    devices: dict[str, set[str]] = {}
    last_seen: dict[str, str] = {}
    cursor = mongo_db["canonical_events"].find(
        {"timestamp": {"$gte": since}}, {"user_id": 1, "device_id": 1, "timestamp": 1}
    )
    async for doc in cursor:
        account = doc.get("user_id") or ""
        key = account_key(account)
        if not key or key in linked or key.startswith(NON_PERSON_ACCOUNTS):
            continue
        counts[account] += 1
        if doc.get("device_id"):
            devices.setdefault(account, set()).add(doc["device_id"])
        stamp = str(doc.get("timestamp") or "")
        if stamp > last_seen.get(account, ""):
            last_seen[account] = stamp
    return UnmappedListOut(
        days=days,
        accounts=[
            UnmappedAccountOut(
                account=account,
                events=n,
                devices=sorted(devices.get(account, set())),
                last_seen=last_seen.get(account),
            )
            for account, n in counts.most_common(200)
        ],
    )


@router.get("/{employee_id}", response_model=EmployeeOut, summary="One employee", dependencies=READ)
async def get_employee(employee_id: str, session: AsyncSession = Depends(get_db)) -> EmployeeOut:
    try:
        return EmployeeOut.from_employee(await _service(session).get(employee_id))
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc


# ─── Changes ────────────────────────────────────────────────


@router.post(
    "/import",
    response_model=ImportOut,
    summary="Import employees from CSV (ITBIS layout or CERT LDAP export)",
    dependencies=MANAGE,
)
async def import_employees(
    file: UploadFile = File(...), session: AsyncSession = Depends(get_db)
) -> ImportOut:
    try:
        result = await _service(session).import_csv(await file.read())
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    _changed()
    return ImportOut(**result.__dict__)


@router.post(
    "",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee",
    dependencies=MANAGE,
)
async def create_employee(
    payload: EmployeeCreate, session: AsyncSession = Depends(get_db)
) -> EmployeeOut:
    employee = Employee(**{**payload.model_dump(), "email": payload.email and str(payload.email)})
    try:
        saved = await _service(session).create(employee)
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    return EmployeeOut.from_employee(saved)


@router.patch(
    "/{employee_id}", response_model=EmployeeOut, summary="Update an employee", dependencies=MANAGE
)
async def update_employee(
    employee_id: str, payload: EmployeeUpdate, session: AsyncSession = Depends(get_db)
) -> EmployeeOut:
    changes = payload.model_dump(exclude_unset=True)
    if "email" in changes and changes["email"] is not None:
        changes["email"] = str(changes["email"])
    try:
        saved = await _service(session).update(employee_id, changes)
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    _changed()
    return EmployeeOut.from_employee(saved)


@router.post(
    "/{employee_id}/accounts",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Link an account to an employee",
    dependencies=MANAGE,
)
async def link_account(
    employee_id: str, payload: AccountLink, session: AsyncSession = Depends(get_db)
) -> EmployeeOut:
    try:
        saved = await _service(session).link_account(
            employee_id, payload.account, payload.account_type
        )
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    _changed()
    return EmployeeOut.from_employee(saved)


@router.delete(
    "/{employee_id}/accounts/{account_id}",
    response_model=EmployeeOut,
    summary="Unlink an account",
    dependencies=MANAGE,
)
async def unlink_account(
    employee_id: str, account_id: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> EmployeeOut:
    try:
        saved = await _service(session).unlink_account(employee_id, account_id)
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    _changed()
    return EmployeeOut.from_employee(saved)


@router.post(
    "/{employee_id}/devices",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a device to an employee",
    dependencies=MANAGE,
)
async def assign_device(
    employee_id: str, payload: DeviceAssign, session: AsyncSession = Depends(get_db)
) -> EmployeeOut:
    try:
        saved = await _service(session).assign_device(
            employee_id, payload.device_id, payload.dedicated
        )
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    return EmployeeOut.from_employee(saved)


@router.delete(
    "/{employee_id}/devices/{device_uuid}",
    response_model=EmployeeOut,
    summary="Unassign a device",
    dependencies=MANAGE,
)
async def unassign_device(
    employee_id: str, device_uuid: uuid.UUID, session: AsyncSession = Depends(get_db)
) -> EmployeeOut:
    try:
        saved = await _service(session).unassign_device(employee_id, device_uuid)
    except DirectoryError as exc:
        raise await _refused(session, exc) from exc
    return EmployeeOut.from_employee(saved)
