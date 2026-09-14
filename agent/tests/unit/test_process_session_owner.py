"""
Unit tests: attributing short-lived processes to the signed-in user by session.
"""

from __future__ import annotations

import pytest

from itbis_agent import normalizer as normalizer_module
from itbis_agent.config import AgentConfig
from itbis_agent.normalizer import Normaliser


def _cfg(**overrides) -> AgentConfig:
    return AgentConfig(
        device_id="WS-TEST", device_name="WS-TEST", source_dataset="win_endpoint", **overrides
    )


def _launch(**extra) -> dict:
    return {
        "source": "process",
        "process_name": "bash.exe",
        "process_id": 4242,
        "command_line": "bash -c true",
        "user": None,
        "owner_sid": None,
        "time_generated": "2026-09-14T16:34:21+00:00",
        **extra,
    }


@pytest.fixture(autouse=True)
def _sessions(monkeypatch):
    signed_in = {1: ("Vishw", "vishwa")}
    monkeypatch.setattr(
        normalizer_module, "session_user", lambda sid: signed_in.get(sid, (None, None))
    )


def test_exited_process_is_attributed_to_the_user_of_its_session():
    ev = Normaliser(_cfg()).normalise(_launch(session_id=1))
    assert ev.user_id == "VISHWA\\vishw"
    assert "owner_from_session" in ev.tags and "owner_unresolved" not in ev.tags
    assert ev.raw_payload["session_id"] == 1


def test_session_zero_is_services_and_dropped_as_noise():
    assert Normaliser(_cfg()).normalise(_launch(session_id=0)) is None
    kept = Normaliser(_cfg(include_system_activity=True)).normalise(_launch(session_id=0))
    assert kept.user_id == "NT AUTHORITY\\SYSTEM"


def test_a_session_nobody_is_signed_in_to_stays_unknown():
    ev = Normaliser(_cfg()).normalise(_launch(session_id=7))
    assert ev.user_id == "unknown" and "owner_unresolved" in ev.tags


def test_a_resolved_owner_is_not_second_guessed():
    ev = Normaliser(_cfg()).normalise(
        _launch(user="VISHWA\\vishw", owner_sid="S-1-5-21-1-2-3-1001", session_id=0)
    )
    assert ev.user_id == "VISHWA\\vishw"
