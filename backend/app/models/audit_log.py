"""
AuditLog model — immutable record of every guardrail decision.

One row is written per SDK call. Algorand TX ID is populated
asynchronously by the Celery task after the on-chain submission completes.

action values:  'BLOCKED' | 'ALLOWED' | 'REDACTED'
hook_type:      'access' | 'pre_execution' | 'post_execution'
violation_type: 'prompt_injection' | 'pii_detected' | 'policy_violation' | NULL
severity:       'low' | 'medium' | 'high' | 'critical'
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class AuditLog(Base):
    """Corresponds to the `audit_logs` table."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id = Column(String(64))
    hook_type = Column(String(20), nullable=False)
    action = Column(String(20), nullable=False)
    violation_type = Column(String(50))
    severity = Column(String(10), nullable=False, default="medium")
    # First 200 chars of the (redacted) input for context — never raw PII
    input_preview = Column(Text)
    # e.g. {"matched_policy": "...", "confidence": 0.95, "pii_types_found": [...]}
    details = Column(JSONB, default={})
    # SHA-256 of full redacted message (for tamper detection)
    payload_hash = Column(String(64))
    policy_version = Column(Integer)
    # Populated by Celery after on-chain submission (Phase 5/6)
    algorand_tx_id = Column(String(64))
    processing_ms = Column(Integer)
    ip_address = Column(INET)
    user_agent = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    tenant = relationship("Tenant", back_populates="audit_logs")
