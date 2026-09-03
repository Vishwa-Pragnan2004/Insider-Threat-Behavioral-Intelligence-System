"""
ITBIS — Unit tests for each supported CERT log parser.

For every parser we verify:
- happy-path row produces a CanonicalEvent with the correct event_type
- column-alias variations are accepted
- malformed rows raise MalformedRecordError
"""
import pytest

from app.modules.activity.application.parsers.device_parser import DeviceParser
from app.modules.activity.application.parsers.email_parser import EmailParser
from app.modules.activity.application.parsers.file_parser import FileParser
from app.modules.activity.application.parsers.http_parser import HttpParser
from app.modules.activity.application.parsers.ldap_parser import LdapParser
from app.modules.activity.application.parsers.logon_parser import LogonParser
from app.modules.activity.application.parsers.psychometric_parser import PsychometricParser
from app.modules.activity.domain.exceptions import MalformedRecordError
from app.shared.schemas.canonical_event import EventType

JOB_ID = "11111111-1111-1111-1111-111111111111"


# ─── Logon ───────────────────────────────────────────────────


def test_logon_parser_happy_path():
    parser = LogonParser()
    row = {
        "id": "1",
        "date": "01/02/2010 08:04:42",
        "user": "ABC123",
        "pc": "PC-001",
        "activity": "Logon",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.LOGON
    assert event.user_id == "ABC123"
    assert event.device_id == "PC-001"
    assert event.source_dataset == "cert"
    assert event.timestamp.year == 2010
    assert event.timestamp.tzinfo is not None


def test_logon_parser_logoff():
    parser = LogonParser()
    row = {"date": "01/02/2010 17:00:00", "user": "u1", "activity": "Logoff"}
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.LOGOFF


def test_logon_parser_failed():
    parser = LogonParser()
    row = {"date": "01/02/2010 17:00:00", "user": "u1", "activity": "Failed Logon"}
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.LOGON_FAILED
    assert event.result == "failure"


def test_logon_parser_alias_columns():
    parser = LogonParser()
    row = {
        "userid": "u1",          # alias for user
        "timestamp": "01/02/2010 08:00:00",  # alias for date
        "activity": "Logon",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.user_id == "u1"
    assert event.timestamp.year == 2010


def test_logon_parser_missing_user_raises():
    parser = LogonParser()
    with pytest.raises(MalformedRecordError):
        parser.parse_row({"date": "01/02/2010 08:00:00", "activity": "Logon"}, 2, JOB_ID)


# ─── Device / USB ────────────────────────────────────────────


def test_device_parser_connect():
    parser = DeviceParser()
    row = {
        "id": "1",
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "pc": "PC1",
        "activity": "Connect",
        "file_tree": "C:\\Users\\u1\\file.txt",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.USB_INSERT
    assert event.target_resource.endswith("file.txt")


def test_device_parser_disconnect():
    parser = DeviceParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "activity": "Disconnect",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.USB_REMOVE


# ─── File ────────────────────────────────────────────────────


def test_file_parser_open():
    parser = FileParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "filename": "C:/secret.docx",
        "activity": "Open",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.FILE_READ
    assert event.target_resource == "C:/secret.docx"


def test_file_parser_delete():
    parser = FileParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "filename": "a.txt",
        "activity": "Delete",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.FILE_DELETE


# ─── Email ───────────────────────────────────────────────────


def test_email_parser_internal_send():
    parser = EmailParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1@dtaa.com",
        "to": "u2@dtaa.com",
        "activity": "send",
        "size": "1024",
        "attachments": "0",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.EMAIL_SENT
    assert event.bytes_transferred == 1024


def test_email_parser_external_detected():
    parser = EmailParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1@dtaa.com",
        "to": "attacker@evil.com",
        "activity": "send",
        "size": "9999",
        "attachments": "1",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.EMAIL_EXTERNAL
    assert "external_email" in event.risk_indicators
    assert "has_attachments" in event.risk_indicators


# ─── HTTP ────────────────────────────────────────────────────


def test_http_parser_request():
    parser = HttpParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "url": "http://www.google.com",
        "activity": "visit",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.HTTP_REQUEST
    assert "google.com" in (event.enrichments or {}).get("domain", "")


def test_http_parser_upload_detected():
    parser = HttpParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "url": "https://dropbox.com/upload",
        "activity": "POST",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.HTTP_UPLOAD
    assert "data_upload_detected" in event.risk_indicators


# ─── LDAP ────────────────────────────────────────────────────


def test_ldap_parser_query():
    parser = LdapParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "u1",
        "activity": "ldap_query",
        "object_accessed": "OU=Finance,DC=dtaa,DC=com",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.LDAP_QUERY


def test_ldap_parser_group_change():
    parser = LdapParser()
    row = {
        "date": "01/02/2010 08:00:00",
        "user": "admin1",
        "activity": "group_change",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.event_type == EventType.GROUP_CHANGE


# ─── Psychometric / HR ──────────────────────────────────────


def test_psychometric_parser_minimal():
    parser = PsychometricParser()
    row = {
        "employee_id": "EMP001",
        "name": "Alice Doe",
        "email": "alice@dtaa.com",
        "role": "Engineer",
        "department": "R&D",
    }
    event = parser.parse_row(row, row_number=2, job_id=JOB_ID)
    assert event.user_id == "EMP001"
    assert event.action == "hr_record"
    assert event.enrichments.get("full_name") == "Alice Doe"
    assert event.department == "R&D"


def test_psychometric_parser_missing_employee_id_raises():
    parser = PsychometricParser()
    with pytest.raises(MalformedRecordError):
        parser.parse_row({"name": "Bob"}, row_number=2, job_id=JOB_ID)
