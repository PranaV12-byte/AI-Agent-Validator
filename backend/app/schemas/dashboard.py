"""Pydantic schemas for dashboard APIs."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsageTrend(BaseModel):
    """Daily usage metrics for dashboard trend charts."""

    date: date
    total_requests: int
    blocked_count: int
    allowed_count: int
    redacted_count: int
    avg_latency_ms: float


class DashboardStats(BaseModel):
    """Top-level counters displayed on dashboard."""

    total_requests_today: int
    blocked_today: int
    allowed_today: int
    redacted_today: int
    block_rate_percent: float
    avg_latency_ms: float
    active_policies: int
    chain_verified_count: int


class DashboardResponse(BaseModel):
    """Dashboard aggregate response."""

    stats: DashboardStats
    trends: list[UsageTrend]


class SafetyConfigUpdate(BaseModel):
    """Partial update payload for tenant safety configuration."""

    injection_protection: bool | None = None
    injection_sensitivity: str | None = Field(default=None, max_length=20)
    pii_redaction: bool | None = None
    pii_types: list[str] | None = None
    policy_enforcement: bool | None = None
    fail_mode: str | None = Field(default=None, max_length=20)
    fallback_message: str | None = None


class SafetyConfigResponse(BaseModel):
    """Safety configuration response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    injection_protection: bool
    injection_sensitivity: str
    pii_redaction: bool
    pii_types: list[str]
    policy_enforcement: bool
    fail_mode: str
    fallback_message: str
    created_at: datetime
    updated_at: datetime
