"""
ITBIS — Identity Module: Domain Exceptions
All domain-level errors for the identity bounded context.
Never expose internal messages directly to HTTP responses.
"""


class IdentityError(Exception):
    """Base class for all identity domain errors."""


class UserAlreadyExistsError(IdentityError):
    """Raised when registering a user with an email/username that already exists."""


class UserNotFoundError(IdentityError):
    """Raised when a user lookup by ID, email, or username finds nothing."""


class InvalidCredentialsError(IdentityError):
    """Raised when login credentials (email/password) do not match."""


class AccountDisabledError(IdentityError):
    """Raised when an inactive/disabled user attempts to authenticate."""


class AccountNotVerifiedError(IdentityError):
    """Raised when an unverified user attempts a restricted action."""


class PermissionDeniedError(IdentityError):
    """Raised when a user lacks the required permission for an action."""


class TokenExpiredError(IdentityError):
    """Raised when a JWT or refresh token has expired."""


class TokenInvalidError(IdentityError):
    """Raised when a token is malformed, tampered, or unrecognised."""


class TokenRevokedError(IdentityError):
    """Raised when a refresh token has been revoked (e.g., after logout)."""


class WeakPasswordError(IdentityError):
    """Raised when a supplied password does not meet strength requirements."""
