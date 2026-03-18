"""Pydantic schemas for authentication APIs."""

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
    api_key: str
