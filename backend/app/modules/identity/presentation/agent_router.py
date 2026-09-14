"""
ITBIS — Identity Module: Agent Device Enrollment API

    POST   /api/v1/agents/enroll            enroll a device, mint its key
    GET    /api/v1/agents                   list enrolled devices
    POST   /api/v1/agents/{device_id}/rotate  issue a fresh key
    DELETE /api/v1/agents/{device_id}       revoke a device's credential

Every route requires `agents:manage`.  A device's own credential grants only
`agent:ingest` and can never manage enrollment.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.modules.identity.application.services.agent_device_service import (
    AgentDeviceService,
    DeviceAlreadyEnrolledError,
    DeviceNotFoundError,
)
from app.modules.identity.domain.agent_device import AgentDevice
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.presentation.agent_dependencies import (
    get_agent_device_service,
)
from app.modules.identity.presentation.dependencies import (
    require_active_user,
    require_permission,
)

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────


class EnrollRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=255)
    device_name: str = Field(..., min_length=1, max_length=255)


class DeviceOut(BaseModel):
    """A device as returned by list/revoke — never carries a secret."""

    id: uuid.UUID
    device_id: str
    device_name: str
    key_reference: str
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None


class EnrollResponse(BaseModel):
    """
    Enrollment result.  `api_key` is shown exactly once — it is not stored
    in recoverable form and cannot be retrieved later.
    """

    device: DeviceOut
    api_key: str
    warning: str = (
        "Copy this key into the agent's config now — it will not be shown again. "
        "If it is lost, rotate the device's key to issue a new one."
    )


def _to_out(d: AgentDevice) -> DeviceOut:
    return DeviceOut(
        id=d.id,
        device_id=d.device_id,
        device_name=d.device_name,
        key_reference=d.key_reference,
        is_active=d.is_active,
        created_at=d.created_at,
        last_seen_at=d.last_seen_at,
        revoked_at=d.revoked_at,
    )


# ─── Routes ──────────────────────────────────────────────────


@router.post(
    "/enroll",
    response_model=EnrollResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll an endpoint agent and mint its credential",
    dependencies=[Depends(require_permission(PermissionName.AGENTS_MANAGE))],
)
async def enroll_device(
    payload: EnrollRequest,
    service: AgentDeviceService = Depends(get_agent_device_service),
    current_user: User = Depends(require_active_user),
):
    try:
        device, api_key = await service.enroll(
            device_id=payload.device_id,
            device_name=payload.device_name,
            created_by=current_user.id,
        )
    except DeviceAlreadyEnrolledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return EnrollResponse(device=_to_out(device), api_key=api_key)


@router.get(
    "",
    response_model=list[DeviceOut],
    summary="List enrolled endpoint agents",
    dependencies=[Depends(require_permission(PermissionName.AGENTS_MANAGE))],
)
async def list_devices(
    service: AgentDeviceService = Depends(get_agent_device_service),
):
    return [_to_out(d) for d in await service.list_devices()]


@router.post(
    "/{device_id}/rotate",
    response_model=EnrollResponse,
    summary="Issue a fresh credential for an enrolled device",
    dependencies=[Depends(require_permission(PermissionName.AGENTS_MANAGE))],
)
async def rotate_device_key(
    device_id: str,
    service: AgentDeviceService = Depends(get_agent_device_service),
):
    try:
        device, api_key = await service.rotate_key(device_id)
    except DeviceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return EnrollResponse(device=_to_out(device), api_key=api_key)


@router.delete(
    "/{device_id}",
    response_model=DeviceOut,
    summary="Revoke an endpoint agent's credential",
    dependencies=[Depends(require_permission(PermissionName.AGENTS_MANAGE))],
)
async def revoke_device(
    device_id: str,
    service: AgentDeviceService = Depends(get_agent_device_service),
):
    try:
        device = await service.revoke(device_id)
    except DeviceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _to_out(device)
