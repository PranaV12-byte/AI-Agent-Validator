"""Pydantic schemas for authentication APIs."""

import re
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"[0-9]")


class SignupRequest(BaseModel):
    """Request body for tenant signup."""

    company_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        if not _HAS_LETTER.search(value):
            raise ValueError("Password must contain at least one letter.")
        if not _HAS_DIGIT.search(value):
            raise ValueError("Password must contain at least one number.")
        return value


class LoginRequest(BaseModel):
    """Request body for tenant login."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    """Auth response payload containing JWT and API key."""

    access_token: str
    token_type: str = "bearer"
    api_key: str | None = None
    refresh_token: str | None = None


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional request body for logout — revokes refresh token if provided."""

    refresh_token: str | None = None


class TenantProfileResponse(BaseModel):
    """Authenticated tenant profile payload."""

    id: UUID
    company_name: str
    email: str
    api_key_prefix: str
    active_policy_version: int


class RegenerateApiKeyResponse(BaseModel):
    """One-time API key rotation response."""

    api_key: str
    api_key_prefix: str


class ForgotPasswordRequest(BaseModel):
    """Request body for password reset initiation."""

    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    """Response after requesting a password reset."""

    message: str
    # Populated only in development so the user can action the link immediately.
    reset_url: str | None = None


class ResetPasswordRequest(BaseModel):
    """Request body for confirming a password reset."""

    token: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        if not _HAS_LETTER.search(value):
            raise ValueError("Password must contain at least one letter.")
        if not _HAS_DIGIT.search(value):
            raise ValueError("Password must contain at least one number.")
        return value
