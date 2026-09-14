"""
ITBIS — Identity Module: Agent Authentication Dependencies

The event-ingest endpoint accepts two kinds of caller:

  1. An enrolled device presenting its own `itbis_ag_*` credential.  This is
     how real endpoint agents authenticate — each device holds a distinct,
     individually revocable key.
  2. A human/service user holding the `agent:ingest` permission.  This keeps
     scripted ingestion (demo pipelines, back-fills, tests) working without
     minting a fake device.

`AgentPrincipal` tells the endpoint which of the two it got, so submissions
can be attributed correctly in the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.identity.application.services.agent_device_service import (
    AgentDeviceService,
)
from app.modules.identity.domain.agent_device import AgentDevice, parse_key
from app.modules.identity.domain.entities import User
from app.modules.identity.domain.enums import PermissionName
from app.modules.identity.infrastructure.agent_device_repository import (
    SQLAgentDeviceRepository,
)
from app.modules.identity.presentation.dependencies import (
    get_current_user,
    oauth2_scheme,
)


@dataclass(frozen=True)
class AgentPrincipal:
    """Who submitted a batch of agent events."""

    kind: str                       # "device" | "user"
    identifier: str                 # device_id, or the user's UUID
    display_name: str
    device: AgentDevice | None = None
    user: User | None = None


def get_agent_device_service(
    db: AsyncSession = Depends(get_db),
) -> AgentDeviceService:
    return AgentDeviceService(SQLAgentDeviceRepository(db))


async def require_agent_ingest(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AgentPrincipal:
    """
    Authenticate an ingest caller as either an enrolled device or a
    permitted user.  Raises 401/403 exactly like the user-only path did.
    """
    # ─── Device credential ──────────────────────────────────
    if parse_key(token) is not None:
        service = AgentDeviceService(SQLAgentDeviceRepository(db))
        device = await service.authenticate(token)
        if device is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked agent credential",
                headers={"WWW-Authenticate": "Bearer"},
            )
        await db.commit()  # persist last_seen_at
        return AgentPrincipal(
            kind="device",
            identifier=device.device_id,
            display_name=device.device_name,
            device=device,
        )

    # ─── Fall back to a user JWT ────────────────────────────
    user = await get_current_user(token=token, db=db)
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is disabled",
        )
    if not user.has_permission(PermissionName.AGENT_INGEST):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Not enough privileges. Requires: "
                f"{PermissionName.AGENT_INGEST.value} "
                f"(or an enrolled device credential)"
            ),
        )
    return AgentPrincipal(
        kind="user",
        identifier=str(user.id),
        display_name=user.username,
        user=user,
    )
