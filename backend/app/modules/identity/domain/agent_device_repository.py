"""
ITBIS — Identity Module: Agent Device Repository Interface
"""

from abc import ABC, abstractmethod

from app.modules.identity.domain.agent_device import AgentDevice


class IAgentDeviceRepository(ABC):
    """Abstract contract for enrolled-device persistence."""

    @abstractmethod
    async def get_by_device_id(self, device_id: str) -> AgentDevice | None:
        """Find an enrolled device by its agent-reported device_id."""
        raise NotImplementedError

    @abstractmethod
    async def get_by_key_reference(self, key_reference: str) -> AgentDevice | None:
        """Find an enrolled device by the plaintext half of its credential."""
        raise NotImplementedError

    @abstractmethod
    async def list_all(self) -> list[AgentDevice]:
        """All enrolled devices, newest first. Never returns secrets."""
        raise NotImplementedError

    @abstractmethod
    async def save(self, device: AgentDevice) -> AgentDevice:
        """Insert or update a device."""
        raise NotImplementedError

    @abstractmethod
    async def delete(self, device_id: str) -> bool:
        """Remove a device entirely. Returns False if it did not exist."""
        raise NotImplementedError
