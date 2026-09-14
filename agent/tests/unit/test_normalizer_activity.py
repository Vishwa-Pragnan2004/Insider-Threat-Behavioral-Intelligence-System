"""Normalisation of removable-drive file activity, downloads and network connections."""
from __future__ import annotations

import pytest

from itbis_agent import normalizer as normalizer_module
from itbis_agent.config import AgentConfig
from itbis_agent.normalizer import Normaliser
from itbis_agent.schemas import EventType

USER_SID = "S-1-5-21-823331484-1016666011-1433572944-1001"
USB_FILE = "D:\\projects\\budget.xlsx"
DOWNLOADS = "C:\\Users\\vishw\\Downloads\\"


@pytest.fixture(autouse=True)
def _console_user(monkeypatch):
    # Windows reports the same account with different casing per API.
    monkeypatch.setattr(normalizer_module, "interactive_user", lambda: ("Vishw", "vishwa"))


def _cfg(**overrides) -> AgentConfig:
    return AgentConfig(
        device_id="WS-TEST", device_name="WS-TEST", source_dataset="win_endpoint", **overrides
    )


@pytest.fixture
def normaliser() -> Normaliser:
    return Normaliser(_cfg())


@pytest.fixture
def keep_system() -> Normaliser:
    return Normaliser(_cfg(include_system_activity=True))


# ─── Removable drive files ──────────────────────────────────


def _removable(kind: str, **extra) -> dict:
    return {
        "source": "removable_files",
        "kind": kind,
        "drive": "D:",
        "volume_name": "SANDISK",
        "path": USB_FILE,
        "relative_path": "projects\\budget.xlsx",
        "old_path": None,
        "size": 4096,
        "time_generated": "2026-09-14T09:40:00+00:00",
        **extra,
    }


def test_file_created_on_a_usb_drive_is_a_copy_to_removable_media(normaliser):
    ev = normaliser.normalise(_removable("created"))
    assert ev.event_type == EventType.FILE_COPY
    assert ev.user_id == "VISHWA\\vishw"
    assert ev.target_resource == USB_FILE
    assert ev.target_type == "removable_media"
    assert ev.bytes_transferred == 4096
    assert ev.file_count == 1
    assert ev.risk_indicators == ["file_copied_to_removable_media"]
    assert ev.enrichments["volume_name"] == "SANDISK"
    assert ev.enrichments["extension"] == ".xlsx"


@pytest.mark.parametrize(
    ("kind", "event_type", "indicators", "transferred"),
    [
        ("modified", EventType.FILE_WRITE, ["file_written_to_removable_media"], 4096),
        ("deleted", EventType.FILE_DELETE, [], None),
        ("renamed", EventType.FILE_MOVE, [], None),
    ],
)
def test_other_changes_on_a_usb_drive(normaliser, kind, event_type, indicators, transferred):
    ev = normaliser.normalise(_removable(kind))
    assert ev.event_type == event_type
    assert ev.risk_indicators == indicators
    assert ev.bytes_transferred == transferred


def test_rename_keeps_the_old_path(normaliser):
    ev = normaliser.normalise(_removable("renamed", old_path="D:\\projects\\draft.xlsx"))
    assert ev.enrichments["old_path"] == "D:\\projects\\draft.xlsx"


def test_scan_summary_is_a_data_transfer(normaliser):
    raw = _removable("data_transfer", path="D:\\", size=10_240, file_count=3, relative_path=None)
    ev = normaliser.normalise(raw)
    assert ev.event_type == EventType.DATA_TRANSFER
    assert ev.bytes_transferred == 10_240
    assert ev.file_count == 3
    assert ev.risk_indicators == ["data_transfer_to_removable_media"]
    assert "extension" not in ev.enrichments


def test_unknown_change_kind_is_ignored(normaliser):
    assert normaliser.normalise(_removable("teleported")) is None


def test_same_file_copied_twice_is_two_distinct_events(normaliser):
    first = normaliser.normalise(_removable("created"))
    later = normaliser.normalise(_removable("created", time_generated="2026-09-14T09:50:00+00:00"))
    assert first.idempotency_key() != later.idempotency_key()


# ─── Downloads ──────────────────────────────────────────────


def _download(name: str = "invoice.pdf", **extra) -> dict:
    return {
        "source": "downloads",
        "path": DOWNLOADS + name,
        "file_name": name,
        "size": 2048,
        "zone_id": "3",
        "host_url": "https://files.example.com/" + name,
        "referrer_url": "https://mail.example.com/",
        "time_generated": "2026-09-14T09:41:00+00:00",
        **extra,
    }


def test_download_records_where_it_came_from(normaliser):
    ev = normaliser.normalise(_download())
    assert ev.event_type == EventType.FILE_DOWNLOAD
    assert ev.user_id == "VISHWA\\vishw"
    assert ev.bytes_transferred == 2048
    assert ev.enrichments["zone_name"] == "Internet"
    assert ev.enrichments["source_host"] == "files.example.com"
    assert ev.enrichments["referrer_url"] == "https://mail.example.com/"
    assert ev.risk_indicators == []


def test_downloaded_executable_is_flagged(normaliser):
    ev = normaliser.normalise(_download("setup.exe"))
    assert ev.risk_indicators == ["executable_downloaded"]


def test_download_without_a_source_url(normaliser):
    ev = normaliser.normalise(_download(host_url=None, referrer_url=None))
    assert "source_host" not in ev.enrichments


# ─── Network ────────────────────────────────────────────────


def _tcp(**extra) -> dict:
    return {
        "source": "network",
        "kind": "tcp_connection",
        "direction": "outbound",
        "local_address": "10.0.0.2",
        "local_port": 50000,
        "remote_address": "93.184.216.34",
        "remote_port": 443,
        "process_id": 100,
        "process_name": "chrome.exe",
        "user": "VISHWA\\vishw",
        "owner_sid": USER_SID,
        "time_generated": "2026-09-14T09:42:00+00:00",
        **extra,
    }


def test_outbound_connection_is_attributed_to_the_process_owner(normaliser):
    ev = normaliser.normalise(_tcp())
    assert ev.event_type == EventType.NETWORK_CONNECTION
    assert ev.user_id == "VISHWA\\vishw"
    assert ev.target_resource == "93.184.216.34:443"
    assert ev.target_type == "network_endpoint"
    assert ev.enrichments["remote_scope"] == "public"
    assert ev.enrichments["process_name"] == "chrome.exe"
    assert ev.is_remote is None


def test_inbound_connection_is_remote(normaliser):
    ev = normaliser.normalise(_tcp(direction="inbound"))
    assert ev.is_remote is True
    assert "inbound" in ev.tags


def test_ipv6_endpoint_is_bracketed(normaliser):
    ev = normaliser.normalise(_tcp(remote_address="2606:4700::6810:84e5"))
    assert ev.target_resource == "[2606:4700::6810:84e5]:443"


def test_lan_peer_is_private(normaliser):
    ev = normaliser.normalise(_tcp(remote_address="192.168.1.20"))
    assert ev.enrichments["remote_scope"] == "private"


def test_system_owned_connection_is_dropped_unless_kept(normaliser, keep_system):
    raw = _tcp(user="NT AUTHORITY\\SYSTEM", owner_sid="S-1-5-18", process_name="System")
    assert normaliser.normalise(raw) is None
    assert keep_system.normalise(raw) is not None


def test_connection_with_an_unresolved_owner(normaliser):
    ev = normaliser.normalise(_tcp(user=None, owner_sid=None, process_name=None))
    assert ev.user_id == "unknown"
    assert "owner_unresolved" in ev.tags


# ─── One identity per person ────────────────────────────────


def test_every_source_names_the_same_person_the_same_way(normaliser):
    """Regression: one person appeared as `vishw`, `VISHWA\\vishw` and `Vishw`."""
    usb_file = normaliser.normalise(_removable("created"))
    download = normaliser.normalise(_download())
    connection = normaliser.normalise(_tcp(user="vishwa\\VISHW"))
    launch = normaliser.normalise(
        {
            "source": "process",
            "process_name": "notepad.exe",
            "process_id": 42,
            "user": "VISHWA\\vishw",
            "owner_sid": USER_SID,
            "time_generated": "2026-09-14T09:43:00+00:00",
        }
    )
    assert {usb_file.user_id, download.user_id, connection.user_id, launch.user_id} == {
        "VISHWA\\vishw"
    }


def test_no_console_user_and_no_environment_is_unknown(normaliser, monkeypatch):
    monkeypatch.setattr(normalizer_module, "interactive_user", lambda: (None, None))
    assert normaliser.normalise(_download()).user_id == "unknown"


def test_service_accounts_keep_their_windows_spelling(keep_system):
    raw = _tcp(user="nt authority\\SYSTEM", owner_sid="S-1-5-18")
    assert keep_system.normalise(raw).user_id == "NT AUTHORITY\\SYSTEM"


def test_user_principal_names_are_lower_cased():
    assert Normaliser._format_user("JSmith@Corp.Example") == "jsmith@corp.example"

