"""
ITBIS — Identity Module: Agent Device Repository (PostgreSQL)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.domain.agent_device import AgentDevice
from app.modules.identity.domain.agent_device_repository import IAgentDeviceRepository
from app.modules.identity.infrastructure.models import AgentDeviceModel


class SQLAgentDeviceRepository(IAgentDeviceRepository):
    """SQLAlchemy implementation of IAgentDeviceRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── Mapping ────────────────────────────────────────────

    @staticmethod
    def _to_domain(m: AgentDeviceModel) -> AgentDevice:
        return AgentDevice(
            id=m.id,
            device_id=m.device_id,
            device_name=m.device_name,
            key_reference=m.key_reference,
            key_hash=m.key_hash,
            is_active=m.is_active,
            created_at=m.created_at,
            created_by=m.created_by,
            last_seen_at=m.last_seen_at,
            revoked_at=m.revoked_at,
        )

    # ─── Queries ────────────────────────────────────────────

    async def get_by_device_id(self, device_id: str) -> AgentDevice | None:
        res = await self.session.execute(
            select(AgentDeviceModel).where(AgentDeviceModel.device_id == device_id)
        )
        m = res.scalar_one_or_none()
        return self._to_domain(m) if m else None

    async def get_by_key_reference(self, key_reference: str) -> AgentDevice | None:
        res = await self.session.execute(
            select(AgentDeviceModel).where(
                AgentDeviceModel.key_reference == key_reference
            )
        )
        m = res.scalar_one_or_none()
        return self._to_domain(m) if m else None

    async def list_all(self) -> list[AgentDevice]:
        res = await self.session.execute(
            select(AgentDeviceModel).order_by(AgentDeviceModel.created_at.desc())
        )
        return [self._to_domain(m) for m in res.scalars().all()]

    # ─── Writes ─────────────────────────────────────────────

    async def save(self, device: AgentDevice) -> AgentDevice:
        res = await self.session.execute(
            select(AgentDeviceModel).where(AgentDeviceModel.id == device.id)
        )
        m = res.scalar_one_or_none()
        if m is None:
            m = AgentDeviceModel(id=device.id)
            self.session.add(m)

        m.device_id = device.device_id
        m.device_name = device.device_name
        m.key_reference = device.key_reference
        m.key_hash = device.key_hash
        m.is_active = device.is_active
        m.created_at = device.created_at
        m.created_by = device.created_by
        m.last_seen_at = device.last_seen_at
        m.revoked_at = device.revoked_at

        await self.session.flush()
        return device

    async def delete(self, device_id: str) -> bool:
        res = await self.session.execute(
            select(AgentDeviceModel).where(AgentDeviceModel.device_id == device_id)
        )
        m = res.scalar_one_or_none()
        if m is None:
            return False
        await self.session.delete(m)
        await self.session.flush()
        return True
