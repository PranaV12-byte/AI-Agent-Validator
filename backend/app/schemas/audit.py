"""Pydantic schemas for audit APIs."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    policy_version: int | None
    algorand_tx_id: str | None
    processing_ms: int | None
    ip_address: IPv4Address | IPv6Address | None
    user_agent: str | None
    created_at: datetime


class AuditListResponse(BaseModel):
    """Paginated audit list response model."""

    logs: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
