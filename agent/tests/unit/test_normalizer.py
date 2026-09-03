"""Tests for the raw-event → CanonicalEvent normaliser."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from itbis_agent.config import AgentConfig
from itbis_agent.normalizer import Normaliser
from itbis_agent.schemas import EventType


@pytest.fixture
def agent_cfg() -> AgentConfig:
    return AgentConfig(
        device_id="WS-DEV-042",
        device_name="WS-DEV-042",
        device_type="workstation",
        operating_system="Windows 11",
        source_dataset="win_endpoint",
    )


@pytest.fixture
def normaliser(agent_cfg) -> Normaliser:
    return Normaliser(agent_cfg)


# ─── Windows Security ───────────────────────────────────────


def test_normalises_successful_logon(normaliser):
    raw = {
        "source": "windows_security",
        "event_id": 4624,
        "record_number": 12345,
        "time_generated": "2026-08-30T08:14:22+00:00",
        "computer": "WS-DEV-042",
        "category": "logon_success",
        "strings": [
            "S-1-0-0",                    # 0
            "DOMAIN",                     # 1
            "DOMAIN",                     # 2
            "0x3e7",                      # 3
            "S-1-5-21-...",               # 4
            "jsmith",                     # 5  TargetUserName
            "DOMAIN",                     # 6  TargetDomainName
            "0x1f2c1b",                   # 7
            "2",                          # 8  LogonType
            "User32",                     # 9
            "Negotiate",                  # 10
            "WS-DEV-042",                 # 11 WorkstationName
            "{...}",                      # 12
            "-",                          # 13
            "-",                          # 14
            "0",                          # 15
            "0x0",                        # 16
            "lsass.exe",                  # 17
            "10.0.42.15",                 # 18 IpAddress
            "51413",                      # 19 IpPort
        ],
    }
    ev = normaliser.normalise(raw)
    assert ev is not None
    assert ev.event_type == EventType.LOGON
    assert ev.user_id == "DOMAIN\\jsmith"
    assert ev.username == "DOMAIN\\jsmith"
    assert ev.device_id == "WS-DEV-042"
    assert ev.ip_address == "10.0.42.15"
    assert ev.action == "4624"
    assert ev.result == "success"
    assert ev.raw_event_id == "4624-12345"
    assert ev.enrichments.get("logon_type") == "2"
    assert "logon_success" in ev.tags


def test_normalises_failed_logon(normaliser):
    raw = {
        "source": "windows_security",
        "event_id": 4625,
        "record_number": 99,
        "time_generated": "2026-08-30T08:14:22+00:00",
        "computer": "WS-DEV-042",
        "category": "logon_failed",
        "strings": ["x"] * 6 + ["DOMAIN", "0", "3"] + ["x"] * 6 + ["10.0.0.1", "5555"],
    }
    ev = normaliser.normalise(raw)
    assert ev is not None
    assert ev.event_type == EventType.LOGON_FAILED
    assert ev.result == "failure"


def test_normalises_logoff(normaliser):
    raw = {
        "source": "windows_security",
        "event_id": 4634,
        "record_number": 7,
        "time_generated": "2026-08-30T17:00:00+00:00",
        "computer": "WS-DEV-042",
        "category": "logoff",
        "strings": ["x", "alice", "DOMAIN", "0x1"],
    }
    ev = normaliser.normalise(raw)
    assert ev is not None
    assert ev.event_type == EventType.LOGOFF
    assert ev.user_id == "DOMAIN\\alice"


def test_normaliser_skips_event_with_no_user(normaliser):
    raw = {
        "source": "windows_security",
        "event_id": 4624,
        "record_number": 1,
        "category": "logon_success",
        "strings": [],
    }
    assert normaliser.normalise(raw) is None


# ─── Process creation ───────────────────────────────────────


def test_normalises_process_creation(normaliser):
    raw = {
        "source": "process",
        "event_id": 4688,
        "time_generated": "2026-08-30T08:14:22+00:00",
        "process_name": "powershell.exe",
        "process_id": 4321,
        "parent_process_id": 1234,
        "command_line": "powershell.exe -enc ...",
        "user": "DOMAIN\\jsmith",
    }
    ev = normaliser.normalise(raw)
    assert ev is not None
    assert ev.event_type == EventType.APP_LAUNCH
    assert ev.user_id == "DOMAIN\\jsmith"
    assert ev.target_resource == "powershell.exe -enc ..."
    assert ev.raw_event_id == "4688-4321"
    assert ev.raw_payload["parent_process_id"] == 1234


def test_normaliser_skips_process_with_no_name(normaliser):
    raw = {"source": "process", "event_id": 4688, "process_id": 1}
    assert normaliser.normalise(raw) is None


# ─── USB ─────────────────────────────────────────────────────


def test_normalises_usb_insert(normaliser):
    raw = {
        "source": "usb",
        "event_id": 2003,
        "kind": "insert",
        "device_id": "E:",
        "volume_name": "USB_DRIVE",
        "file_system": "FAT32",
        "size_bytes": 8_000_000_000,
    }
    ev = normaliser.normalise(raw)
    assert ev is not None
    assert ev.event_type == EventType.USB_INSERT
    assert ev.target_resource == "E:"
    assert ev.target_type == "usb_device"


def test_normalises_usb_remove(normaliser):
    raw = {
        "source": "usb",
        "event_id": 2100,
        "kind": "remove",
        "device_id": "E:",
    }
    ev = normaliser.normalise(raw)
    assert ev is not None
    assert ev.event_type == EventType.USB_REMOVE


# ─── Idempotency key ────────────────────────────────────────


def test_idempotency_key_uses_raw_event_id():
    from itbis_agent.schemas import CanonicalEvent

    ev = CanonicalEvent(
        event_id=uuid.uuid4(),
        event_type=EventType.LOGON,
        source_dataset="win_endpoint",
        raw_event_id="4624-12345",
        timestamp=datetime.now(UTC),
        user_id="x",
    )
    assert ev.idempotency_key() == "win_endpoint:4624-12345"


def test_idempotency_key_falls_back_to_event_id():
    from itbis_agent.schemas import CanonicalEvent

    ev = CanonicalEvent(
        event_type=EventType.LOGON,
        source_dataset="win_endpoint",
        timestamp=datetime.now(UTC),
        user_id="x",
    )
    key = ev.idempotency_key()
    assert key.startswith("win_endpoint:")


# ─── Robustness ──────────────────────────────────────────────


def test_unknown_source_returns_none(normaliser):
    assert normaliser.normalise({"source": "unknown"}) is None


def test_empty_dict_returns_none(normaliser):
    assert normaliser.normalise({}) is None
