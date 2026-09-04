"""
ITBIS — Identity Module: API Schemas
Pydantic models for HTTP requests and responses.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─── Requests ────────────────────────────────────────────────

class RegisterUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(...)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(...)


class UpdateUserRequest(BaseModel):
    full_name: str | None = Field(None, max_length=100)
    email: EmailStr | None = None


# ─── Responses ───────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserProfileResponse(BaseModel):
    id: str
    username: str
    email: EmailStr
    full_name: str
    roles: list[str]
    permissions: list[str]
    is_superadmin: bool

    model_config = ConfigDict(from_attributes=True)
