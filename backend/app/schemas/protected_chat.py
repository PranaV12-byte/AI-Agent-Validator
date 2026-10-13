"""Authenticated request and response models for the local protected-chat demo."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


ProtectedChatStatus = Literal[
    "allowed",
    "redacted",
    "blocked",
    "evaluation_failed",
    "provider_unavailable",
    "service_unavailable",
    "busy",
]


class ProtectedChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class ProtectedChatResponse(BaseModel):
    conversation_id: UUID
    status: ProtectedChatStatus
    answer: str | None = None
    fallback_message: str | None = None
    error_code: str | None = None
    input_redacted: bool = False
    output_redacted: bool = False
    policy_version: int
    audit_ids: list[UUID] = Field(default_factory=list)


class ProtectedChatReadiness(BaseModel):
    ready: bool
    error_code: str | None = None
    model: str
