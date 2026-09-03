"""
ITBIS — Unit tests for the parser registry.

Verifies column-signature auto-detection for every supported log type
and that unknown schemas raise UnsupportedLogTypeError.
"""
import pytest

from app.modules.activity.application.parsers.registry import (
    detect_parser,
    get_parser_for_type,
    get_registered_log_types,
)
from app.modules.activity.domain.enums import LogType
from app.modules.activity.domain.exceptions import UnsupportedLogTypeError

# ─── Column signatures for each CERT log type ───────────────

LOGON_COLS = {"id", "date", "user", "pc", "activity"}
DEVICE_COLS = {"id", "date", "user", "pc", "activity", "file_tree"}
FILE_COLS = {"id", "date", "user", "pc", "filename", "activity"}
EMAIL_COLS = {"id", "date", "user", "pc", "to", "from", "activity", "size", "attachments"}
HTTP_COLS = {"id", "date", "user", "pc", "url", "activity"}
LDAP_COLS = {"id", "date", "user", "pc", "activity", "object_accessed"}
PSYCHOMETRIC_COLS = {"employee_id", "name", "role", "department"}


# ─── Detection ──────────────────────────────────────────────


def test_detect_logon_parser():
    p = detect_parser(LOGON_COLS)
    assert p.LOG_TYPE == LogType.LOGON


def test_detect_device_parser():
    p = detect_parser(DEVICE_COLS)
    assert p.LOG_TYPE == LogType.DEVICE


def test_detect_file_parser():
    p = detect_parser(FILE_COLS)
    assert p.LOG_TYPE == LogType.FILE


def test_detect_email_parser():
    p = detect_parser(EMAIL_COLS)
    assert p.LOG_TYPE == LogType.EMAIL


def test_detect_http_parser():
    p = detect_parser(HTTP_COLS)
    assert p.LOG_TYPE == LogType.HTTP


def test_detect_ldap_parser():
    p = detect_parser(LDAP_COLS)
    assert p.LOG_TYPE == LogType.LDAP


def test_detect_psychometric_parser():
    p = detect_parser(PSYCHOMETRIC_COLS)
    assert p.LOG_TYPE == LogType.PSYCHOMETRIC


def test_detect_unknown_columns_raises():
    with pytest.raises(UnsupportedLogTypeError):
        detect_parser({"foo", "bar", "baz"})


def test_detect_empty_columns_raises():
    with pytest.raises(UnsupportedLogTypeError):
        detect_parser(set())


def test_detection_is_case_insensitive():
    p = detect_parser({c.upper() for c in LOGON_COLS})
    assert p.LOG_TYPE == LogType.LOGON


# ─── Explicit lookups ───────────────────────────────────────


def test_get_parser_for_type_known():
    p = get_parser_for_type(LogType.FILE)
    assert p.LOG_TYPE == LogType.FILE


def test_get_parser_for_type_unknown_enum():
    # If an enum value isn't registered, UnsupportedLogTypeError is raised
    # UNKNOWN isn't registered, so this should fail
    with pytest.raises(UnsupportedLogTypeError):
        get_parser_for_type(LogType.UNKNOWN)


# ─── Registry completeness ──────────────────────────────────


def test_all_log_types_registered():
    types = get_registered_log_types()
    assert LogType.LOGON in types
    assert LogType.DEVICE in types
    assert LogType.FILE in types
    assert LogType.EMAIL in types
    assert LogType.HTTP in types
    assert LogType.LDAP in types
    assert LogType.PSYCHOMETRIC in types


def test_file_preferred_over_logon_for_filename():
    """Both FileParser and LogonParser could match a CSV with user+date+activity.
    The registry must prefer FileParser when 'filename' is present.
    """
    cols = {"user", "date", "activity", "filename", "pc", "id"}
    p = detect_parser(cols)
    assert p.LOG_TYPE == LogType.FILE


def test_http_preferred_for_url_column():
    cols = {"user", "date", "url", "activity", "pc"}
    p = detect_parser(cols)
    assert p.LOG_TYPE == LogType.HTTP
