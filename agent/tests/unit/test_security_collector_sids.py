"""
SID resolution in the Windows Security collector.

Local group membership and user-right events log the affected account as "-"
with only a SID. The collector resolves it on the host, the only place a local
SID can be mapped to a name.
"""
from __future__ import annotations

import sys

import pytest

from itbis_agent.collectors import windows_security as ws

MEMBER_SID = "S-1-5-21-1-2-3-1005"
ACTOR_SID = "S-1-5-21-1-2-3-1001"


def test_group_event_resolves_only_the_member_field(monkeypatch):
    looked_up: list[str] = []

    def fake_lookup(sid):
        looked_up.append(sid)
        return "WS-TEST\\backdoor"

    monkeypatch.setattr(ws, "lookup_account_sid", fake_lookup)
    strings = ["-", MEMBER_SID, "Administrators", "Builtin", "S-1-5-32-544",
               ACTOR_SID, "jsmith", "WS-TEST", "0x1", "-"]

    assert ws.resolve_sids(4732, strings) == {MEMBER_SID: "WS-TEST\\backdoor"}
    assert looked_up == [MEMBER_SID], "group and actor SIDs are not member fields"


def test_user_right_event_resolves_the_target(monkeypatch):
    monkeypatch.setattr(ws, "lookup_account_sid", lambda sid: "WS-TEST\\backdoor")
    strings = [ACTOR_SID, "jsmith", "WS-TEST", "0x1", MEMBER_SID, "SeDebugPrivilege"]
    assert ws.resolve_sids(4704, strings) == {MEMBER_SID: "WS-TEST\\backdoor"}


def test_placeholders_unknown_sids_and_other_events_are_skipped(monkeypatch):
    monkeypatch.setattr(ws, "lookup_account_sid", lambda sid: None)
    assert ws.resolve_sids(4732, ["-", "-", "Administrators"]) == {}
    assert ws.resolve_sids(4732, ["-", MEMBER_SID, "Administrators"]) == {}
    assert ws.resolve_sids(4624, ["S-1-5-18"] * 20) == {}, "logons carry no SID fields"
    assert ws.resolve_sids(4732, []) == {}


@pytest.mark.skipif(sys.platform != "win32", reason="real LookupAccountSid")
def test_real_lookup_resolves_a_well_known_sid():
    pytest.importorskip("win32security")
    name = ws.lookup_account_sid("S-1-5-32-544")  # BUILTIN\Administrators (localised)
    assert name
    assert "\\" in name


@pytest.mark.skipif(sys.platform != "win32", reason="real LookupAccountSid")
def test_real_lookup_returns_none_for_unknown_or_invalid_sids():
    pytest.importorskip("win32security")
    assert ws.lookup_account_sid("S-1-5-21-1-2-3-999999") is None
    assert ws.lookup_account_sid("not-a-sid") is None
