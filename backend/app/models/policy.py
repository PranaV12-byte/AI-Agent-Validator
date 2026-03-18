"""
Policy model — a business rule that Safebot enforces.

rule_type determines how the rule is evaluated:
  'semantic'  — embedded via SentenceTransformer + pgvector cosine similarity
  'parameter' — checked against JSONB parameters (e.g., max_discount: 10)
  'keyword'   — simple substring/regex match

policy_hash + algorand_tx_id are populated by the Celery task
after the policy is registered on-chain.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Policy(Base):
    """Corresponds to the `policies` table."""

    __tablename__ = "policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text)
    rule_text = Column(Text, nullable=False)
    rule_type = Column(String(50), nullable=False, default="semantic")
    parameters = Column(JSONB, default={})
    is_enabled = Column(Boolean, nullable=False, default=True)
    version = Column(Integer, nullable=False, default=1)
    # Populated after Algorand registration (Phase 5)
    policy_hash = Column(String(64))
    algorand_tx_id = Column(String(64))
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
    tenant = relationship("Tenant", back_populates="policies")
    embeddings = relationship(
        "PolicyEmbedding",
        back_populates="policy",
        cascade="all, delete-orphan",
    )
