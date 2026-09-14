"""
ITBIS — Unit tests: agent device credentials.

Covers key generation/parsing and the AgentDeviceService lifecycle against an
in-memory repository.
"""
from __future__ import annotations

import uuid

import pytest

from app.modules.identity.application.services.agent_device_service import (
    AgentDeviceService,
    DeviceAlreadyEnrolledError,
    DeviceNotFoundError,
)
from app.modules.identity.domain.agent_device import (
    AgentDevice,
    generate_key,
    hash_secret,
    parse_key,
)
from app.modules.identity.domain.agent_device_repository import IAgentDeviceRepository


class FakeAgentDeviceRepository(IAgentDeviceRepository):
    def __init__(self) -> None:
        self.rows: dict[str, AgentDevice] = {}

    async def get_by_device_id(self, device_id):
        return self.rows.get(device_id)

    async def get_by_key_reference(self, key_reference):
        return next(
            (d for d in self.rows.values() if d.key_reference == key_reference), None
        )

    async def list_all(self):
        return list(self.rows.values())

    async def save(self, device):
        self.rows[device.device_id] = device
        return device

    async def delete(self, device_id):
        return self.rows.pop(device_id, None) is not None


@pytest.fixture
def service() -> AgentDeviceService:
    return AgentDeviceService(FakeAgentDeviceRepository())


# ─── Key format ──────────────────────────────────────────────


def test_generated_key_round_trips():
    full_key, reference, key_hash = generate_key()
    parsed = parse_key(full_key)
    assert parsed is not None
    assert parsed[0] == reference
    assert hash_secret(parsed[1]) == key_hash


def test_generated_keys_are_unique():
    keys = {generate_key()[0] for _ in range(100)}
    assert len(keys) == 100


def test_secret_is_not_recoverable_from_hash():
    full_key, _, key_hash = generate_key()
    secret = parse_key(full_key)[1]
    assert secret not in key_hash
    assert len(key_hash) == 64  # sha256 hex


@pytest.mark.parametrize(
    "bad",
    ["", "garbage", "itbis_ag", "itbis_ag_only", "wrong_prefix_aaa_bbb", "itbis_ag__x"],
)
def test_malformed_keys_are_rejected(bad):
    assert parse_key(bad) is None


def test_secret_containing_underscores_survives_parsing():
    """token_urlsafe output can contain underscores — the tail must rejoin."""
    device = AgentDevice(
        id=uuid.uuid4(),
        device_id="d",
        device_name="d",
        key_reference="abc123",
        key_hash=hash_secret("aa_bb_cc"),
    )
    parsed = parse_key("itbis_ag_abc123_aa_bb_cc")
    assert parsed == ("abc123", "aa_bb_cc")
    assert device.verify(parsed[1]) is True


# ─── Enrollment lifecycle ────────────────────────────────────


@pytest.mark.asyncio
async def test_enroll_returns_key_once(service):
    device, api_key = await service.enroll(device_id="WS-1", device_name="Laptop 1")
    assert device.device_id == "WS-1"
    assert device.is_active is True
    assert api_key.startswith("itbis_ag_")
    # The plaintext secret is not retrievable from the stored device.
    assert api_key not in (device.key_hash, device.key_reference)


@pytest.mark.asyncio
async def test_enrolling_same_device_twice_is_rejected(service):
    await service.enroll(device_id="WS-1", device_name="Laptop 1")
    with pytest.raises(DeviceAlreadyEnrolledError):
        await service.enroll(device_id="WS-1", device_name="Laptop 1 again")


@pytest.mark.asyncio
async def test_authenticate_accepts_the_issued_key(service):
    _, api_key = await service.enroll(device_id="WS-1", device_name="Laptop 1")
    device = await service.authenticate(api_key)
    assert device is not None
    assert device.device_id == "WS-1"
    assert device.last_seen_at is not None


@pytest.mark.asyncio
async def test_authenticate_rejects_unknown_and_malformed(service):
    await service.enroll(device_id="WS-1", device_name="Laptop 1")
    assert await service.authenticate("itbis_ag_deadbeef_nope") is None
    assert await service.authenticate("not-a-key") is None
    assert await service.authenticate("") is None


@pytest.mark.asyncio
async def test_authenticate_rejects_wrong_secret_for_real_reference(service):
    device, _ = await service.enroll(device_id="WS-1", device_name="Laptop 1")
    forged = f"itbis_ag_{device.key_reference}_wrongsecret"
    assert await service.authenticate(forged) is None


@pytest.mark.asyncio
async def test_revoked_device_cannot_authenticate(service):
    _, api_key = await service.enroll(device_id="WS-1", device_name="Laptop 1")
    assert await service.authenticate(api_key) is not None

    await service.revoke("WS-1")
    assert await service.authenticate(api_key) is None


@pytest.mark.asyncio
async def test_revoking_one_device_leaves_others_working(service):
    _, key_a = await service.enroll(device_id="WS-A", device_name="A")
    _, key_b = await service.enroll(device_id="WS-B", device_name="B")

    await service.revoke("WS-A")

    assert await service.authenticate(key_a) is None
    assert await service.authenticate(key_b) is not None


@pytest.mark.asyncio
async def test_rotate_invalidates_the_previous_key(service):
    _, old_key = await service.enroll(device_id="WS-1", device_name="Laptop 1")
    _, new_key = await service.rotate_key("WS-1")

    assert old_key != new_key
    assert await service.authenticate(old_key) is None
    assert await service.authenticate(new_key) is not None


@pytest.mark.asyncio
async def test_rotate_reactivates_a_revoked_device(service):
    await service.enroll(device_id="WS-1", device_name="Laptop 1")
    await service.revoke("WS-1")
    _, new_key = await service.rotate_key("WS-1")

    device = await service.authenticate(new_key)
    assert device is not None
    assert device.is_active is True
    assert device.revoked_at is None


@pytest.mark.asyncio
async def test_rotate_and_revoke_require_an_enrolled_device(service):
    with pytest.raises(DeviceNotFoundError):
        await service.rotate_key("nope")
    with pytest.raises(DeviceNotFoundError):
        await service.revoke("nope")
