"""
ITBIS — Identity Module: Agent Device Service

Owns the lifecycle of endpoint-agent credentials: enrollment, rotation,
revocation, and authentication of a presented key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from app.modules.identity.domain.agent_device import (
    AgentDevice,
    generate_key,
    parse_key,
)
from app.modules.identity.domain.agent_device_repository import IAgentDeviceRepository

log = structlog.get_logger(__name__)


class AgentDeviceError(Exception):
    """Base class for enrollment errors."""


class DeviceAlreadyEnrolledError(AgentDeviceError):
    """A device with this device_id is already enrolled."""


class DeviceNotFoundError(AgentDeviceError):
    """No device is enrolled under this device_id."""


class AgentDeviceService:
    """Application service for the agent-device credential lifecycle."""

    def __init__(self, repo: IAgentDeviceRepository) -> None:
        self.repo = repo

    # ─── Enrollment ─────────────────────────────────────────

    async def enroll(
        self,
        *,
        device_id: str,
        device_name: str,
        created_by: uuid.UUID | None = None,
    ) -> tuple[AgentDevice, str]:
        """
        Enroll a new device and mint its credential.

        Returns `(device, full_key)`.  The full key is the only time the
        secret exists outside the agent's config — it is not recoverable.
        """
        existing = await self.repo.get_by_device_id(device_id)
        if existing is not None:
            raise DeviceAlreadyEnrolledError(
                f"device_id {device_id!r} is already enrolled; "
                f"rotate its key instead of re-enrolling"
            )

        full_key, reference, key_hash = generate_key()
        device = AgentDevice(
            id=uuid.uuid4(),
            device_id=device_id,
            device_name=device_name,
            key_reference=reference,
            key_hash=key_hash,
            created_by=created_by,
        )
        await self.repo.save(device)
        log.info(
            "agent_device.enrolled",
            device_id=device_id,
            key_reference=reference,
            created_by=str(created_by) if created_by else None,
        )
        return device, full_key

    async def rotate_key(self, device_id: str) -> tuple[AgentDevice, str]:
        """Issue a fresh credential for an existing device, invalidating the old one."""
        device = await self.repo.get_by_device_id(device_id)
        if device is None:
            raise DeviceNotFoundError(f"device_id {device_id!r} is not enrolled")

        full_key, reference, key_hash = generate_key()
        device.key_reference = reference
        device.key_hash = key_hash
        # Rotating revives a revoked device — the operator is deliberately
        # issuing it a working credential again.
        device.is_active = True
        device.revoked_at = None
        await self.repo.save(device)
        log.info("agent_device.key_rotated", device_id=device_id, key_reference=reference)
        return device, full_key

    async def revoke(self, device_id: str) -> AgentDevice:
        """Disable a device's credential. The row is kept for audit purposes."""
        device = await self.repo.get_by_device_id(device_id)
        if device is None:
            raise DeviceNotFoundError(f"device_id {device_id!r} is not enrolled")
        device.revoke()
        await self.repo.save(device)
        log.info("agent_device.revoked", device_id=device_id)
        return device

    async def list_devices(self) -> list[AgentDevice]:
        return await self.repo.list_all()

    # ─── Authentication ─────────────────────────────────────

    async def authenticate(self, raw_key: str) -> AgentDevice | None:
        """
        Resolve a presented credential to an active device, or None.

        Returns None for every failure mode (malformed, unknown, wrong
        secret, revoked) so a caller cannot distinguish between them.
        """
        parsed = parse_key(raw_key)
        if parsed is None:
            return None
        reference, secret = parsed

        device = await self.repo.get_by_key_reference(reference)
        if device is None:
            return None
        if not device.verify(secret):
            log.warning("agent_device.bad_secret", key_reference=reference)
            return None
        if not device.is_active:
            log.warning("agent_device.revoked_key_used", device_id=device.device_id)
            return None

        device.touch(datetime.now(UTC))
        await self.repo.save(device)
        return device
