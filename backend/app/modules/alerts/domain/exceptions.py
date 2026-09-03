"""
ITBIS — Alerts Module: Domain Exceptions
"""


class AlertError(Exception):
    """Base error for the alerts module."""


class AlertNotFoundError(AlertError):
    """An alert with the given id does not exist."""


class IllegalAlertStatusTransitionError(AlertError):
    """A request asked for an alert status change that violates the lifecycle."""


class DuplicateAlertError(AlertError):
    """
    Raised when the underlying store detected a duplicate idempotency key.

    The application service catches this and converts it to a no-op
    "existing alert returned" response, so callers (including the
    automatic Phase-5 integration) don't need to handle this directly.
    """


class AssigneeNotFoundError(AlertError):
    """The supplied `assigned_to` user id does not exist.

    Raised by AlertService.assign when IUserDirectory.user_exists
    returns False.  The router maps this to HTTP 404.
    """
