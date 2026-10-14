"""Pydantic schemas for audit APIs."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    """Audit log response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    session_id: str | None
    hook_type: str
    action: str
    violation_type: str | None
    severity: str
    input_preview: str | None
    details: dict[str, Any]
    payload_hash: str | None
    payload_hash_provenance: Literal["stored_unverified", "unavailable"]
    policy_version: int | None
    algorand_tx_id: str | None
    processing_ms: int | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    redacted_fields: list[str] = Field(default_factory=list)
    anchoring_status: Literal["anchored", "pending", "disabled", "not_anchored"] = "pending"
    review_status: Literal["open", "resolved"] | None = None


class AuditListResponse(BaseModel):
    """Paginated audit list response model."""

    logs: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
