"""
ITBIS — Investigations Module: Domain Enums
"""
from enum import Enum

from app.modules.alerts.domain.enums import AlertSeverity


class InvestigationStatus(str, Enum):
    """
    Lifecycle:

        OPEN
            -> IN_PROGRESS
        IN_PROGRESS
            -> RESOLVED
            -> OPEN        (analyst reopens)
        RESOLVED
            -> CLOSED
            -> IN_PROGRESS  (analyst reopens for further work)
        CLOSED        (terminal)
    """

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


_VALID_TRANSITIONS: dict[InvestigationStatus, set[InvestigationStatus]] = {
    InvestigationStatus.OPEN: {InvestigationStatus.IN_PROGRESS},
    InvestigationStatus.IN_PROGRESS: {
        InvestigationStatus.RESOLVED,
        InvestigationStatus.OPEN,
    },
    InvestigationStatus.RESOLVED: {
        InvestigationStatus.CLOSED,
        InvestigationStatus.IN_PROGRESS,
    },
    InvestigationStatus.CLOSED: set(),
}


def allowed_next_statuses(current: InvestigationStatus) -> set[InvestigationStatus]:
    return _VALID_TRANSITIONS.get(current, set())


def is_valid_transition(
    current: InvestigationStatus, target: InvestigationStatus
) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


# Severity is shared with the alerts module so the whole UI vocabulary
# is consistent.  We re-export for callers that prefer a single import.
__all__ = [
    "InvestigationStatus",
    "AlertSeverity",
    "allowed_next_statuses",
    "is_valid_transition",
]
