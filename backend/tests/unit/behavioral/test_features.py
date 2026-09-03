"""
ITBIS — Unit tests for the behavioral feature extractor.
"""
from datetime import UTC, datetime

import pytest

from app.modules.behavioral.application.features import (
    FEATURE_DEFINITIONS,
    event_field,
    feature_names,
    is_email,
    is_external_email,
    is_failed_logon,
    is_file_activity,
    is_file_copy,
    is_http_activity,
    is_ldap_activity,
    is_logon,
    is_process_activity,
    is_usb_activity,
)
from app.modules.behavioral.domain.enums import FEATURE_NAMES

# ─── Feature name contract ─────────────────────────────────


def test_feature_names_returns_canonical_order():
    names = feature_names()
    assert names == FEATURE_NAMES
    assert names[0] == "total_activity_count"
    assert names[-1] == "activity_type_diversity"
    assert len(names) == 16


def test_every_feature_name_is_defined():
    for n in FEATURE_NAMES:
        assert n in FEATURE_DEFINITIONS, f"missing definition for {n!r}"


def test_feature_definitions_have_consistent_aggregator():
    for name, defn in FEATURE_DEFINITIONS.items():
        assert defn.name == name
        if defn.aggregator == "event_match":
            assert defn.event_match is not None
        if defn.aggregator == "set_size":
            assert defn.field is not None


# ─── Per-event classifier helpers ──────────────────────────


def test_is_logon():
    assert is_logon({"event_type": "logon"})
    assert not is_logon({"event_type": "logoff"})


def test_is_failed_logon():
    assert is_failed_logon({"event_type": "logon_failed"})
    assert not is_failed_logon({"event_type": "logon"})


def test_is_file_activity_matches_all_file_types():
    for et in ("file_read", "file_write", "file_delete", "file_copy", "file_move"):
        assert is_file_activity({"event_type": et})


def test_is_file_copy_only_matches_copy():
    assert is_file_copy({"event_type": "file_copy"})
    assert not is_file_copy({"event_type": "file_read"})


def test_is_usb_activity_matches_all_usb_types():
    for et in ("usb_insert", "usb_remove", "usb_file_copy"):
        assert is_usb_activity({"event_type": et})


def test_is_email_matches_all_email_types():
    for et in ("email_sent", "email_received", "email_external"):
        assert is_email({"event_type": et})


def test_is_external_email():
    assert is_external_email({"event_type": "email_external"})
    assert is_external_email({"event_type": "email_sent", "risk_indicators": ["external_email"]})
    assert not is_external_email({"event_type": "email_sent", "risk_indicators": []})


def test_is_http_activity():
    assert is_http_activity({"event_type": "http_request"})
    assert is_http_activity({"event_type": "http_upload"})


def test_is_ldap_activity():
    for et in (
        "ldap_query",
        "privilege_change",
        "group_change",
        "account_created",
        "account_disabled",
        "password_change",
    ):
        assert is_ldap_activity({"event_type": et})
    assert not is_ldap_activity({"event_type": "logon"})


def test_is_process_activity():
    for et in ("app_launch", "app_close", "app_install"):
        assert is_process_activity({"event_type": et})
    assert not is_process_activity({"event_type": "logon"})


# ─── event_field helper ────────────────────────────────────


def test_event_field_hour_of_day():
    ev = {"timestamp": datetime(2026, 8, 30, 14, 30, tzinfo=UTC)}
    assert event_field(ev, "hour_of_day") == 14


def test_event_field_hour_of_day_handles_strings():
    ev = {"timestamp": "2026-08-30T14:30:00+00:00"}
    assert event_field(ev, "hour_of_day") == 14


def test_event_field_hour_of_day_handles_missing():
    assert event_field({}, "hour_of_day") is None


def test_event_field_device_id():
    assert event_field({"device_id": "WS-1"}, "device_id") == "WS-1"
    assert event_field({"device_id": None}, "device_id") is None
    assert event_field({}, "device_id") is None


def test_event_field_target_resource():
    assert event_field({"target_resource": "/etc/passwd"}, "target_resource") == "/etc/passwd"


def test_event_field_event_type():
    assert event_field({"event_type": "logon"}, "event_type") == "logon"


def test_event_field_unknown_raises():
    with pytest.raises(KeyError):
        event_field({}, "unknown_field")
