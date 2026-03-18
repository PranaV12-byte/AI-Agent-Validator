"""Pydantic schemas for policy APIs."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PolicyCreate(BaseModel):
    """Request body for creating a policy."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    rule_text: str = Field(min_length=1)
    rule_type: str = Field(default="semantic", max_length=50)
    parameters: dict[str, Any] | None = None


class PolicyUpdate(BaseModel):
    """Request body for updating a policy."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    rule_text: str | None = Field(default=None, min_length=1)
    rule_type: str | None = Field(default=None, max_length=50)
    parameters: dict[str, Any] | None = None
    is_enabled: bool | None = None


class PolicyResponse(BaseModel):
    """Policy response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    rule_text: str
    rule_type: str
    parameters: dict[str, Any]
    is_enabled: bool
    version: int
    policy_hash: str | None
    algorand_tx_id: str | None
    created_at: datetime
    updated_at: datetime


class PolicyListResponse(BaseModel):
    """Paginated-lite list response for policies."""

    policies: list[PolicyResponse]
    total: int
