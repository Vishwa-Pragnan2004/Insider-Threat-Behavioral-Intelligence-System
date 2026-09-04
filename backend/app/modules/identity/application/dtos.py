"""
ITBIS — Identity Module: Application DTOs
Data Transfer Objects used strictly within the application layer.
They decouple Use Cases from the HTTP Presentation layer schemas.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RegisterUserDTO:
    username: str
    email: str
    password: str
    full_name: str = ""


@dataclass
class LoginDTO:
    email: str
    password: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


@dataclass
class TokenPairDTO:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


@dataclass
class UserProfileDTO:
    id: str
    username: str
    email: str
    full_name: str
    roles: list[str]
    permissions: list[str]
    is_superadmin: bool


@dataclass
class UpdateUserDTO:
    full_name: str | None = None
    email: str | None = None
