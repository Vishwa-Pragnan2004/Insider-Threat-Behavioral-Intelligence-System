"""
ITBIS — Investigations Module: Domain Exceptions
"""


class InvestigationError(Exception):
    """Base error for the investigations module."""


class InvestigationNotFoundError(InvestigationError):
    """An investigation with the given id does not exist."""


class IllegalInvestigationStatusTransitionError(InvestigationError):
    """A request asked for a status change that violates the lifecycle."""


class InvestigationNoteError(InvestigationError):
    """Base error for note operations."""


class InvestigationNoteNotFoundError(InvestigationNoteError):
    """A note with the given id does not exist."""


class InvestigationNoteImmutableError(InvestigationNoteError):
    """A request tried to modify or delete an immutable note."""


class AssigneeNotFoundError(InvestigationError):
    """The supplied `assigned_to` user id does not exist.

    Raised by InvestigationService.assign when IUserDirectory.user_exists
    returns False.  The router maps this to HTTP 404.
    """
