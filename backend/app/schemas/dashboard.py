"""Pydantic schemas for dashboard APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DashboardStats(BaseModel):
    """Top-level counters displayed on dashboard home."""

    total_requests: int
    blocked_requests: int
    avg_latency_ms: float


class DashboardResponse(BaseModel):
    """Dashboard summary response."""

    total_requests: int
    blocked_requests: int
    avg_latency_ms: float


class SafetyConfigUpdate(BaseModel):
    """Partial update payload for tenant safety configuration."""

    global_block_enabled: bool | None = None
    injection_protection: bool | None = None
    injection_sensitivity: str | None = Field(default=None, max_length=20)
    pii_redaction: bool | None = None
    pii_types: list[str] | None = None
    policy_enforcement: bool | None = None
    fail_mode: str | None = Field(default=None, max_length=20)
    fallback_message: str | None = None
    log_retention_days: int | None = Field(default=None, ge=1)


class SafetyConfigResponse(BaseModel):
    """Safety configuration response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    global_block_enabled: bool
    injection_protection: bool
    injection_sensitivity: str
    pii_redaction: bool
    pii_types: list[str]
    policy_enforcement: bool
    fail_mode: str
    fallback_message: str
    log_retention_days: int
    created_at: datetime
    updated_at: datetime
