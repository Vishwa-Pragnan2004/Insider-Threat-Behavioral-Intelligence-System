"""
ITBIS — Identity Module: Token Service
Handles JWT creation and verification.
Wraps python-jose to abstract the underlying implementation.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt

from app.core.config import get_settings
from app.modules.identity.domain.exceptions import TokenExpiredError, TokenInvalidError


class TokenService:
    """Service for encoding and decoding JWTs."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def create_access_token(self, subject: str, claims: dict[str, Any]) -> str:
        """
        Create a short-lived access token.
        
        Args:
            subject: The primary subject (usually user ID).
            claims: Additional claims (e.g., roles, permissions).
            
        Returns:
            Encoded JWT string.
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        payload = {
            "sub": subject,
            "iat": now,
            "exp": expire,
            "type": "access",
            **claims,
        }
        
        return jwt.encode(
            payload,
            self.settings.SECRET_KEY,
            algorithm=self.settings.JWT_ALGORITHM,
        )

    def create_refresh_token(self, subject: str, jti: str) -> str:
        """
        Create a long-lived refresh token.
        
        Args:
            subject: The primary subject (user ID).
            jti: JWT ID (unique identifier for revocation).
            
        Returns:
            Encoded JWT string.
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        payload = {
            "sub": subject,
            "jti": jti,
            "iat": now,
            "exp": expire,
            "type": "refresh",
        }
        
        return jwt.encode(
            payload,
            self.settings.SECRET_KEY,
            algorithm=self.settings.JWT_ALGORITHM,
        )

    def decode_token(self, token: str, expected_type: str = "access") -> Dict[str, Any]:
        """
        Decode and verify a JWT.
        
        Args:
            token: The encoded JWT.
            expected_type: Either "access" or "refresh".
            
        Returns:
            The decoded payload dictionary.
            
        Raises:
            TokenExpiredError: If the token has expired.
            TokenInvalidError: If the token is malformed, tampered, or wrong type.
        """
        try:
            payload = jwt.decode(
                token,
                self.settings.SECRET_KEY,
                algorithms=[self.settings.JWT_ALGORITHM],
            )
            
            if payload.get("type") != expected_type:
                raise TokenInvalidError(f"Expected {expected_type} token")
                
            return payload
            
        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError("Token has expired") from e
        except JWTError as e:
            raise TokenInvalidError("Invalid token signature or format") from e


# ─── Module-level singleton ───────────────────────────────────
token_service = TokenService()
