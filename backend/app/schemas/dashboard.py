"""Pydantic schemas for dashboard APIs."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DashboardDailyActivity(BaseModel):
    """One UTC calendar day of distinct request totals."""

    date: date
    allowed_requests: int
    redacted_requests: int
    blocked_requests: int
    error_requests: int


class DashboardStats(BaseModel):
    """Top-level counters displayed on dashboard home."""

    total_requests: int
    blocked_requests: int
    allowed_requests: int
    redacted_requests: int
    error_requests: int
    avg_latency_ms: float
    daily_trend: list[DashboardDailyActivity]


class DashboardResponse(BaseModel):
    """Dashboard summary response."""

    total_requests: int
    blocked_requests: int
    allowed_requests: int
    redacted_requests: int
    error_requests: int
    avg_latency_ms: float
    daily_trend: list[DashboardDailyActivity]


class SafetyConfigUpdate(BaseModel):
    """Partial update payload for tenant safety configuration."""

    model_config = ConfigDict(extra="forbid")

    global_block_enabled: bool | None = None
    injection_protection: bool | None = None
    injection_sensitivity: Literal["strict", "moderate", "lenient"] | None = None
    pii_redaction: bool | None = None
    pii_types: list[Literal["aadhaar", "pan", "email", "phone", "upi"]] | None = None
    policy_enforcement: bool | None = None
    fail_mode: Literal["open", "closed"] | None = None
    fallback_message: str | None = Field(default=None, max_length=2000)
    log_retention_days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> "SafetyConfigUpdate":
        null_fields = [
            name
            for name in self.model_fields_set
            if getattr(self, name) is None
        ]
        if null_fields:
            raise ValueError(
                "Fields cannot be null: " + ", ".join(sorted(null_fields))
            )
        return self


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
