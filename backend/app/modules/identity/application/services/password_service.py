"""
ITBIS — Identity Module: Password Service
Wraps passlib/bcrypt for hashing and verification.

SECURITY:
- Plaintext passwords NEVER leave this service.
- Hashes use bcrypt with a cost factor of 12.
- Minimum password length is enforced here.
"""

import re

from passlib.context import CryptContext

from app.modules.identity.domain.exceptions import WeakPasswordError

# ─── bcrypt context ──────────────────────────────────────────
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

_MIN_LENGTH = 8
_PASSWORD_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


class PasswordService:
    """
    Service for password hashing and verification.
    Inject this via FastAPI Depends — do not instantiate per-request.
    """

    def hash(self, plaintext: str) -> str:
        """
        Hash a plaintext password using bcrypt.

        Args:
            plaintext: The raw password provided by the user.

        Returns:
            A bcrypt hash string safe to store in the database.

        Raises:
            WeakPasswordError: If the password does not meet strength requirements.
        """
        self._validate_strength(plaintext)
        return _pwd_context.hash(plaintext)

    def verify(self, plaintext: str, hashed: str) -> bool:
        """
        Verify a plaintext password against a stored bcrypt hash.

        Args:
            plaintext: The raw password provided by the user.
            hashed: The bcrypt hash from the database.

        Returns:
            True if the password matches; False otherwise.

        NOTE: This method is deliberately constant-time to prevent timing attacks.
        """
        return _pwd_context.verify(plaintext, hashed)

    def _validate_strength(self, password: str) -> None:
        """
        Enforce minimum password strength requirements.

        Requirements:
        - At least 8 characters
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit

        Raises:
            WeakPasswordError: If any requirement is not met.
        """
        if not password or len(password) < _MIN_LENGTH:
            raise WeakPasswordError(
                f"Password must be at least {_MIN_LENGTH} characters long."
            )
        if not _PASSWORD_PATTERN.match(password):
            raise WeakPasswordError(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, and one digit."
            )


# ─── Module-level singleton ───────────────────────────────────
password_service = PasswordService()
