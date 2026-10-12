"""Pydantic schemas for SDK hook endpoints."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    """Payload for pre-checking a chatbot message."""

    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=64)


class CheckResponse(BaseModel):
    """Response returned by the /hooks/check endpoint."""

    action: str
    original_message: str | None = None
    sanitized_message: str | None = None
    violations: list[dict[str, Any]]
    processing_ms: int
    audit_id: UUID
    evaluation_status: str = "allowed"
    error_code: str | None = None
    evaluation_failures: list[str] = Field(default_factory=list)


class SanitizeRequest(BaseModel):
    """Payload for sanitizing potentially sensitive text."""

    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=64)


class SanitizeResponse(BaseModel):
    """Response returned by the /hooks/sanitize endpoint."""

    sanitized_message: str
    redactions: list[dict[str, Any]]
    processing_ms: int
    audit_id: UUID
    action: str = "ALLOWED"
    evaluation_status: str = "allowed"
    error_code: str | None = None
    evaluation_failures: list[str] = Field(default_factory=list)


class ValidateRequest(BaseModel):
    """Payload for unified guardrail validation endpoint."""

    prompt: str = Field(min_length=1, max_length=8000)
    user_id: str | None = Field(default=None, max_length=128)


class ValidateResponse(BaseModel):
    """Response returned by /validate endpoint."""

    action: str
    reason: str
    redacted_text: str | None = None
    evaluation_status: str = "allowed"
    error_code: str | None = None
    evaluation_failures: list[str] = Field(default_factory=list)
