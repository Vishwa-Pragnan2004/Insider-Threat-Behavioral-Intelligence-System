"""
Windows Security event mapping: field positions, noise filtering, and the
account / privilege / remote-access events.

Field layouts follow the provider's own templates
(`Get-WinEvent -ListProvider Microsoft-Windows-Security-Auditing`), which is
the only reliable source: every event ID packs its data in a different order.
"""
from __future__ import annotations

import pytest

from itbis_agent.collectors.windows_security import WANTED_EVENT_IDS
from itbis_agent.config import AgentConfig
from itbis_agent.normalizer import (
    _SECURITY_HANDLERS,
    Normaliser,
    is_privileged_group,
    is_service_account,
)
from itbis_agent.schemas import EventType

USER_SID = "S-1-5-21-823331484-1016666011-1433572944-1001"
OTHER_SID = "S-1-5-21-1-2-3-1005"


def _cfg(**overrides) -> AgentConfig:
    return AgentConfig(
        device_id="WS-TEST",
        device_name="WS-TEST",
        source_dataset="win_endpoint",
        **overrides,
    )


@pytest.fixture
def normaliser() -> Normaliser:
    return Normaliser(_cfg())


@pytest.fixture
def keep_system() -> Normaliser:
    return Normaliser(_cfg(include_system_activity=True))


def _raw(event_id: int, strings: list, record: int = 1, sid_names: dict | None = None) -> dict:
    raw = {
        "source": "windows_security",
        "event_id": event_id,
        "record_number": record,
        "time_generated": "2026-09-14T09:00:00+00:00",
        "computer": "WS-TEST",
        "category": WANTED_EVENT_IDS[event_id],
        "strings": strings,
    }
    if sid_names:
        raw["sid_names"] = sid_names
    return raw


def _logon_4624(
    user="jsmith", domain="CORP", sid=USER_SID, logon_type="2", workstation="WS-TEST", ip="-"
) -> list:
    return [
        "S-1-5-18", "WS-TEST$", "WORKGROUP", "0x3e7",   # 0-3 Subject*
        sid, user, domain, "0x1f2c1b",                  # 4-7 Target*
        logon_type, "User32", "Negotiate", workstation,  # 8-11
        "{00000000-0000-0000-0000-000000000000}", "-", "-", "0",  # 12-15
        "0x2a4", r"C:\Windows\System32\svchost.exe", ip, "-",     # 16-19
    ]


def _failed_4625(
    user="jsmith", domain="CORP", logon_type="3", workstation="ATTACKER-PC", ip="10.0.0.99"
) -> list:
    return [
        "S-1-0-0", "-", "-", "0x0",                       # 0-3 Subject*
        "S-1-0-0", user, domain,                          # 4-6 Target*
        "0xc000006d", "%%2313", "0xc000006a",             # 7-9 Status / FailureReason / SubStatus
        logon_type, "NtLmSsp ", "NTLM", workstation,      # 10-13
        "-", "-", "0", "0x0", "-", ip, "445",             # 14-20
    ]


# ─── Registry ───────────────────────────────────────────────


def test_every_collected_event_id_has_a_handler():
    """A collected ID without a handler would be read and silently thrown away."""
    assert set(WANTED_EVENT_IDS) == set(_SECURITY_HANDLERS)


# ─── Logons and noise ───────────────────────────────────────


def test_interactive_logon_by_a_person_is_kept(normaliser):
    ev = normaliser.normalise(_raw(4624, _logon_4624()))
    assert ev.event_type == EventType.LOGON
    assert ev.user_id == "CORP\\jsmith"
    assert ev.enrichments["logon_type"] == "2"
    assert ev.enrichments["logon_type_name"] == "Interactive"
    assert ev.is_remote is False


@pytest.mark.parametrize(
    ("user", "domain", "sid", "logon_type"),
    [
        ("SYSTEM", "NT AUTHORITY", "S-1-5-18", "5"),  # what the agent actually uploaded
        ("DWM-1", "Window Manager", "S-1-5-90-0-1", "2"),
        ("UMFD-0", "Font Driver Host", "S-1-5-96-0-0", "2"),
        ("WS-TEST$", "WORKGROUP", "S-1-5-18", "3"),
        ("jsmith", "CORP", USER_SID, "4"),  # scheduled task
        ("jsmith", "CORP", USER_SID, "5"),  # service running under a user account
    ],
)
def test_non_human_logons_are_dropped(normaliser, user, domain, sid, logon_type):
    raw = _raw(4624, _logon_4624(user, domain, sid, logon_type))
    assert normaliser.normalise(raw) is None


def test_include_system_activity_keeps_them(keep_system):
    raw = _raw(4624, _logon_4624("SYSTEM", "NT AUTHORITY", "S-1-5-18", "5"))
    ev = keep_system.normalise(raw)
    assert ev is not None
    assert ev.user_id == "NT AUTHORITY\\SYSTEM"


def test_remote_desktop_logon_is_remote_access(normaliser):
    raw = _raw(4624, _logon_4624(logon_type="10", workstation="HOME-PC", ip="203.0.113.7"))
    ev = normaliser.normalise(raw)
    assert ev.event_type == EventType.LOGON
    assert ev.is_remote is True
    assert "remote_access" in ev.tags
    assert ev.enrichments["logon_type_name"] == "RemoteInteractive"
    assert ev.enrichments["source_ip"] == "203.0.113.7"


def test_network_logon_from_another_host_is_remote_but_not_a_session(normaliser):
    ev = normaliser.normalise(_raw(4624, _logon_4624(logon_type="3", ip="10.0.0.5")))
    assert ev.is_remote is True
    assert "network_logon" in ev.tags
    assert "remote_access" not in ev.tags


def test_loopback_network_logon_is_not_remote(normaliser):
    ev = normaliser.normalise(_raw(4624, _logon_4624(logon_type="3", ip="127.0.0.1")))
    assert ev.is_remote is False


# ─── Failed logons (regression) ─────────────────────────────


def test_failed_logon_reads_its_own_field_layout(normaliser):
    """
    Regression: 4625 was parsed with 4624's indexes, reading FailureReason as
    the logon type, the process path as the IP, and the logon process as the
    workstation.
    """
    ev = normaliser.normalise(_raw(4625, _failed_4625()))
    assert ev.event_type == EventType.LOGON_FAILED
    assert ev.result == "failure"
    assert ev.user_id == "CORP\\jsmith"
    assert ev.enrichments["logon_type"] == "3"
    assert ev.enrichments["failure_status"] == "0xc000006d"
    assert ev.enrichments["failure_sub_status"] == "0xc000006a"
    assert ev.ip_address == "10.0.0.99"
    assert ev.device_name == "ATTACKER-PC"
    assert ev.is_remote is True


def test_failed_logon_with_null_sid_is_not_discarded(normaliser):
    """TargetUserSid is S-1-0-0 for most failures — it must not mark the account as a service."""
    ev = normaliser.normalise(_raw(4625, _failed_4625(user="administrator", domain="-")))
    assert ev is not None
    assert ev.user_id == "administrator"


# ─── Logoffs ────────────────────────────────────────────────


def test_service_logoff_is_dropped(normaliser):
    raw = _raw(4634, ["S-1-5-18", "SYSTEM", "NT AUTHORITY", "0x3e7", "5"])
    assert normaliser.normalise(raw) is None


def test_user_initiated_logoff_is_kept(normaliser):
    ev = normaliser.normalise(_raw(4647, [USER_SID, "jsmith", "CORP", "0x1f2c1b"]))
    assert ev.event_type == EventType.LOGOFF
    assert ev.user_id == "CORP\\jsmith"


# ─── Account lifecycle ──────────────────────────────────────


def _account(target="backdoor", actor="jsmith") -> list:
    # TargetUserName, TargetDomainName, TargetSid, SubjectUserSid,
    # SubjectUserName, SubjectDomainName, SubjectLogonId, PrivilegeList
    return [target, "WS-TEST", OTHER_SID, USER_SID, actor, "WS-TEST", "0x1f2c1b", "-"]


def test_account_created_is_attributed_to_the_creator(normaliser):
    ev = normaliser.normalise(_raw(4720, _account()))
    assert ev.event_type == EventType.ACCOUNT_CREATED
    assert ev.user_id == "WS-TEST\\jsmith"
    assert ev.target_resource == "WS-TEST\\backdoor"
    assert ev.target_type == "user_account"
    assert "account_created" in ev.risk_indicators


@pytest.mark.parametrize(
    ("event_id", "event_type", "change"),
    [
        (4722, EventType.PRIVILEGE_CHANGE, "enabled"),
        (4723, EventType.PASSWORD_CHANGE, "password_changed"),
        (4724, EventType.PASSWORD_CHANGE, "password_reset"),
        (4725, EventType.ACCOUNT_DISABLED, "disabled"),
        (4726, EventType.ACCOUNT_DISABLED, "deleted"),
    ],
)
def test_account_lifecycle_mapping(normaliser, event_id, event_type, change):
    ev = normaliser.normalise(_raw(event_id, _account()))
    assert ev.event_type == event_type
    assert ev.enrichments["change"] == change


def test_resetting_someone_elses_password_is_flagged(normaliser):
    ev = normaliser.normalise(_raw(4724, _account(target="alice", actor="jsmith")))
    assert "password_reset_of_other_account" in ev.risk_indicators


def test_resetting_your_own_password_is_not_flagged(normaliser):
    ev = normaliser.normalise(_raw(4724, _account(target="jsmith", actor="jsmith")))
    assert ev.risk_indicators == []


def test_account_changes_are_kept_even_when_made_by_system(normaliser):
    """Unlike logons, account changes are always security-relevant."""
    strings = ["defaultuser0", "WS-TEST", OTHER_SID, "S-1-5-18", "WS-TEST$", "WORKGROUP", "0x3e7"]
    assert normaliser.normalise(_raw(4720, strings)) is not None


# ─── Group membership ───────────────────────────────────────


def _group(
    member_name="-",
    member_sid=OTHER_SID,
    group="Administrators",
    group_domain="Builtin",
    group_sid="S-1-5-32-544",
    actor="jsmith",
) -> list:
    # MemberName, MemberSid, TargetUserName, TargetDomainName, TargetSid,
    # SubjectUserSid, SubjectUserName, SubjectDomainName, SubjectLogonId, PrivilegeList
    return [
        member_name, member_sid, group, group_domain, group_sid,
        USER_SID, actor, "WS-TEST", "0x1f2c1b", "-",
    ]


def test_adding_someone_to_administrators_is_a_privilege_change(normaliser):
    sid_names = {OTHER_SID: "WS-TEST\\backdoor"}
    ev = normaliser.normalise(_raw(4732, _group(), sid_names=sid_names))
    assert ev.event_type == EventType.PRIVILEGE_CHANGE
    assert ev.user_id == "WS-TEST\\jsmith"
    assert ev.target_resource == "Builtin\\Administrators"
    assert ev.enrichments["member"] == "WS-TEST\\backdoor"
    assert ev.enrichments["group_scope"] == "local"
    assert ev.enrichments["privileged_group"] is True
    assert "privileged_group_member_added" in ev.risk_indicators
    assert ev.raw_payload["sid_names"] == sid_names


def test_privileged_group_is_recognised_by_sid_not_name(normaliser):
    """German Windows names it "Administratoren"; the SID is what identifies it."""
    ev = normaliser.normalise(_raw(4732, _group(group="Administratoren")))
    assert ev.event_type == EventType.PRIVILEGE_CHANGE


def test_ordinary_group_change_is_a_group_change(normaliser):
    raw = _raw(
        4733,
        _group(group="Marketing", group_domain="CORP", group_sid="S-1-5-21-1-2-3-2104"),
    )
    ev = normaliser.normalise(raw)
    assert ev.event_type == EventType.GROUP_CHANGE
    assert ev.enrichments["change"] == "member_removed"
    assert ev.risk_indicators == []


def test_domain_admins_membership_is_privileged(normaliser):
    raw = _raw(
        4728,
        _group(
            member_name="CN=Bob,OU=Staff,DC=corp,DC=local",
            group="Domain Admins",
            group_domain="CORP",
            group_sid="S-1-5-21-1-2-3-512",
        ),
    )
    ev = normaliser.normalise(raw)
    assert ev.event_type == EventType.PRIVILEGE_CHANGE
    assert ev.enrichments["group_scope"] == "global"
    assert ev.enrichments["member"] == "CN=Bob,OU=Staff,DC=corp,DC=local"


def test_unresolved_member_falls_back_to_its_sid(normaliser):
    ev = normaliser.normalise(_raw(4732, _group()))
    assert ev.enrichments["member"] == OTHER_SID


# ─── User rights ────────────────────────────────────────────


def test_sensitive_user_right_assignment_is_flagged(normaliser):
    strings = [USER_SID, "jsmith", "WS-TEST", "0x1f2c1b", OTHER_SID,
               "SeDebugPrivilege\n\t\t\tSeShutdownPrivilege"]
    ev = normaliser.normalise(_raw(4704, strings, sid_names={OTHER_SID: "WS-TEST\\backdoor"}))
    assert ev.event_type == EventType.PRIVILEGE_CHANGE
    assert ev.user_id == "WS-TEST\\jsmith"
    assert ev.target_resource == "WS-TEST\\backdoor"
    assert ev.enrichments["rights"] == ["SeDebugPrivilege", "SeShutdownPrivilege"]
    assert ev.enrichments["sensitive_rights"] == ["SeDebugPrivilege"]
    assert "sensitive_user_right_assigned" in ev.risk_indicators


def test_removing_a_right_is_not_flagged(normaliser):
    strings = [USER_SID, "jsmith", "WS-TEST", "0x1", OTHER_SID, "SeDebugPrivilege"]
    ev = normaliser.normalise(_raw(4705, strings))
    assert ev.enrichments["change"] == "right_removed"
    assert ev.risk_indicators == []


# ─── Remote Desktop sessions ────────────────────────────────


def _session(name="RDP-Tcp#3") -> list:
    # AccountName, AccountDomain, LogonID, SessionName, ClientName, ClientAddress
    return ["jsmith", "CORP", "0x1f2c1b", name, "HOME-PC", "203.0.113.7"]


def test_rdp_reconnect_is_a_remote_session(normaliser):
    ev = normaliser.normalise(_raw(4778, _session()))
    assert ev.event_type == EventType.REMOTE_SESSION_CONNECT
    assert ev.user_id == "CORP\\jsmith"
    assert ev.is_remote is True
    assert ev.target_resource == "RDP-Tcp#3"
    assert ev.ip_address == "203.0.113.7"
    assert ev.enrichments["client_name"] == "HOME-PC"
    assert "remote_access" in ev.tags


def test_rdp_disconnect_is_a_remote_session_end(normaliser):
    ev = normaliser.normalise(_raw(4779, _session()))
    assert ev.event_type == EventType.REMOTE_SESSION_DISCONNECT


def test_console_session_switch_is_not_remote_access(normaliser):
    assert normaliser.normalise(_raw(4778, _session(name="Console"))) is None


# ─── Classification helpers ─────────────────────────────────


@pytest.mark.parametrize(
    ("sid", "expected"),
    [
        ("S-1-5-32-544", True),  # Administrators
        ("S-1-5-32-555", True),  # Remote Desktop Users
        ("S-1-5-21-1-2-3-512", True),  # Domain Admins
        ("S-1-5-21-1-2-3-519", True),  # Enterprise Admins
        ("S-1-5-32-545", False),  # Users
        ("S-1-5-21-1-2-3-1512", False),  # RID merely ends in 512
        (None, False),
    ],
)
def test_is_privileged_group(sid, expected):
    assert is_privileged_group(sid) is expected


@pytest.mark.parametrize(
    ("name", "domain", "sid", "expected"),
    [
        ("SYSTEM", "NT AUTHORITY", None, True),
        ("anything", None, "S-1-5-19", True),
        ("DWM-3", "Window Manager", None, True),
        ("LAPTOP$", "CORP", None, True),
        ("-", None, None, True),
        ("jsmith", "CORP", USER_SID, False),
        ("vishw", "VISHWA", None, False),
    ],
)
def test_is_service_account(name, domain, sid, expected):
    assert is_service_account(name, domain, sid) is expected


# ─── Process owner attribution ──────────────────────────────


def _process(user=None, owner_sid=None) -> dict:
    return {
        "source": "process",
        "event_id": 4688,
        "time_generated": "20260914140608.000000+330",
        "process_name": "notepad.exe",
        "process_id": 42,
        "parent_process_id": 7,
        "command_line": "notepad.exe",
        "user": user,
        "owner_sid": owner_sid,
    }


def test_process_is_attributed_to_its_owner(normaliser):
    ev = normaliser.normalise(_process("VISHWA\\vishw", USER_SID))
    assert ev.user_id == "VISHWA\\vishw"
    assert ev.raw_payload["owner_sid"] == USER_SID
    assert "owner_unresolved" not in ev.tags


def test_system_owned_process_is_dropped(normaliser):
    assert normaliser.normalise(_process("NT AUTHORITY\\SYSTEM", "S-1-5-18")) is None


def test_system_owned_process_is_kept_when_configured(keep_system):
    assert keep_system.normalise(_process("NT AUTHORITY\\SYSTEM", "S-1-5-18")) is not None


def test_unresolved_owner_is_unknown_not_system(normaliser):
    """Previously every launch was attributed to "SYSTEM" regardless of who ran it."""
    ev = normaliser.normalise(_process())
    assert ev.user_id == "unknown"
    assert "owner_unresolved" in ev.tags
