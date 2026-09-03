"""
ITBIS — Unit tests for the BaseParser utilities.

Exercises column resolution, alias fallback, timestamp parsing,
and int-coercion helpers.
"""
import pytest

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.domain.enums import LogType
from app.modules.activity.domain.exceptions import MalformedRecordError


class _DummyParser(BaseParser):
    LOG_TYPE = LogType.LOGON
    REQUIRED_COLUMNS = {"user", "date"}
    COLUMN_ALIASES = {
        "user": ["userid", "employee"],
        "date": ["timestamp"],
    }

    def parse_row(self, row, row_number, job_id):
        # Not used in these tests
        raise NotImplementedError


@pytest.fixture
def parser() -> _DummyParser:
    return _DummyParser()


# ─── Column resolution ──────────────────────────────────────


def test_resolve_column_direct_match(parser):
    assert parser.resolve_column({"user": "alice"}, "user") == "alice"


def test_resolve_column_strips_whitespace(parser):
    assert parser.resolve_column({"user": "  alice  "}, "user") == "alice"


def test_resolve_column_alias_fallback(parser):
    assert parser.resolve_column({"userid": "alice"}, "user") == "alice"


def test_resolve_column_case_insensitive(parser):
    assert parser.resolve_column({"USER": "alice"}, "user") == "alice"
    assert parser.resolve_column({"UserId": "alice"}, "user") == "alice"


def test_resolve_column_missing_returns_none(parser):
    assert parser.resolve_column({"foo": "bar"}, "user") is None


def test_resolve_column_empty_string_returned(parser):
    # resolve_column returns whatever it finds (including empty strings);
    # resolve_required is responsible for raising on empty.
    assert parser.resolve_column({"user": ""}, "user") == ""


def test_resolve_column_none_value(parser):
    assert parser.resolve_column({"user": None}, "user") is None


def test_resolve_required_missing_raises(parser):
    with pytest.raises(MalformedRecordError) as exc:
        parser.resolve_required({"foo": "bar"}, "user", row_number=42)
    assert exc.value.row_number == 42
    assert "user" in exc.value.reason


def test_resolve_required_present(parser):
    assert parser.resolve_required({"user": "alice"}, "user", row_number=1) == "alice"


def test_resolve_required_empty_string_raises(parser):
    with pytest.raises(MalformedRecordError):
        parser.resolve_required({"user": ""}, "user", row_number=7)


# ─── Timestamp parsing ──────────────────────────────────────


@pytest.mark.parametrize(
    "raw,year",
    [
        ("01/02/2010 08:04:42", 2010),
        ("2010-01-02 08:04:42", 2010),
        ("2010-01-02T08:04:42", 2010),
        ("2010-01-02T08:04:42Z", 2010),
        ("01/02/2010 08:04", 2010),
    ],
)
def test_parse_timestamp_valid_formats(parser, raw, year):
    ts = parser.parse_timestamp(raw, row_number=1)
    assert ts.year == year
    assert ts.tzinfo is not None  # UTC


def test_parse_timestamp_invalid_raises(parser):
    with pytest.raises(MalformedRecordError) as exc:
        parser.parse_timestamp("not a date", row_number=5)
    assert exc.value.row_number == 5


# ─── safe_int ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("10", 10),
        ("3.0", 3),
        ("-5", -5),
        (None, None),
        ("abc", None),
        ("", None),
    ],
)
def test_safe_int(parser, raw, expected):
    assert parser.safe_int(raw) == expected


# ─── can_parse ──────────────────────────────────────────────


def test_can_parse_with_all_required(parser):
    assert _DummyParser.can_parse({"user", "date"}) is True


def test_can_parse_with_extras(parser):
    assert _DummyParser.can_parse({"user", "date", "extra", "fields"}) is True


def test_cannot_parse_missing_required(parser):
    assert _DummyParser.can_parse({"user"}) is False


def test_can_parse_case_insensitive(parser):
    assert _DummyParser.can_parse({"USER", "DATE"}) is True
