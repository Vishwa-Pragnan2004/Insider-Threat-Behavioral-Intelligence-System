"""
ITBIS — Activity Module: Parser Registry

Central registry mapping log types to their parser implementations.
Open/Closed: register new parsers without modifying existing code.
"""

from app.modules.activity.application.parsers.base_parser import BaseParser
from app.modules.activity.application.parsers.device_parser import DeviceParser
from app.modules.activity.application.parsers.email_parser import EmailParser
from app.modules.activity.application.parsers.file_parser import FileParser
from app.modules.activity.application.parsers.http_parser import HttpParser
from app.modules.activity.application.parsers.ldap_parser import LdapParser
from app.modules.activity.application.parsers.logon_parser import LogonParser
from app.modules.activity.application.parsers.psychometric_parser import PsychometricParser
from app.modules.activity.domain.enums import LogType
from app.modules.activity.domain.exceptions import UnsupportedLogTypeError

# Registration order matters: more specific parsers first.
# The registry tries parsers in order and returns the first match.
_REGISTERED_PARSERS: list[type[BaseParser]] = [
    FileParser,          # Requires: user, date, filename, activity
    EmailParser,         # Requires: user, date, activity  (but checked before logon via columns)
    HttpParser,          # Requires: user, date, url
    LdapParser,          # Requires: user, date
    DeviceParser,        # Requires: user, date, activity
    LogonParser,         # Requires: user, date, activity  (most general — last)
    PsychometricParser,  # Requires: employee_id
]


def detect_parser(columns: set[str]) -> BaseParser:
    """
    Auto-detect the correct parser for a CSV based on its column names.

    Args:
        columns: Set of column names from the CSV header row.

    Returns:
        An instantiated parser that can handle the CSV.

    Raises:
        UnsupportedLogTypeError: if no parser matches the columns.
    """
    for parser_cls in _REGISTERED_PARSERS:
        if parser_cls.can_parse(columns):
            return parser_cls()
    raise UnsupportedLogTypeError(
        f"No parser found for columns: {sorted(columns)}. "
        f"Supported log types: {[p.LOG_TYPE.value for p in _REGISTERED_PARSERS]}"
    )


def get_parser_for_type(log_type: LogType) -> BaseParser:
    """Return a parser instance for an explicit log type."""
    for parser_cls in _REGISTERED_PARSERS:
        if parser_cls.LOG_TYPE == log_type:
            return parser_cls()
    raise UnsupportedLogTypeError(f"No parser registered for log type: {log_type.value}")


def get_registered_log_types() -> list[LogType]:
    """Return the list of all currently registered log types."""
    return [p.LOG_TYPE for p in _REGISTERED_PARSERS]
