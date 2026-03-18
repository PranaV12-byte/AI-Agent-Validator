"""
SafetyConfig model — per-tenant guardrail configuration.

One row per tenant (enforced via UNIQUE constraint on tenant_id).
Controls which guardrails are enabled and their sensitivity levels.

fail_mode:
  'closed' — block request on any error (safe default)
  'open'   — allow request on system error (not recommended for production)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class SafetyConfig(Base):
    """Corresponds to the `safety_configs` table."""

    __tablename__ = "safety_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # ── Injection protection ───────────────────────────────────────────────────
    injection_protection = Column(Boolean, nullable=False, default=True)
    # 'strict' | 'moderate' | 'lenient'
    injection_sensitivity = Column(String(20), nullable=False, default="moderate")

    # ── PII redaction ──────────────────────────────────────────────────────────
    pii_redaction = Column(Boolean, nullable=False, default=True)
    # JSON array: ["aadhaar", "pan", "email", "phone", "upi"]
    pii_types = Column(
        JSONB,
        nullable=False,
        default=["aadhaar", "pan", "email", "phone", "upi"],
    )

    # ── Policy enforcement ─────────────────────────────────────────────────────
    policy_enforcement = Column(Boolean, nullable=False, default=True)
    # 'closed' | 'open'
    fail_mode = Column(String(20), nullable=False, default="closed")
    fallback_message = Column(
        Text,
        nullable=False,
        default="I cannot help with that request. A human agent will follow up.",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    tenant = relationship("Tenant", back_populates="safety_config")
