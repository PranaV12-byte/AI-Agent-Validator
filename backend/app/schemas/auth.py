"""Pydantic schemas for authentication APIs."""

from uuid import UUID

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    """Request body for tenant signup."""

    company_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Request body for tenant login."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    """Auth response payload containing JWT and API key."""

    access_token: str
    token_type: str = "bearer"
    api_key: str | None = None


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
