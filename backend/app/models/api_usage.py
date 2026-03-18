"""
ApiUsage model — daily aggregated counters per tenant.

One row per (tenant_id, date) pair (enforced by UniqueConstraint).
Updated via upsert in audit_service after each guardrail decision.
"""

import uuid
from datetime import date

from sqlalchemy import Column, Date, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ApiUsage(Base):
    """Corresponds to the `api_usage` table."""

    __tablename__ = "api_usage"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    date = Column(Date, nullable=False, default=date.today)
    total_requests = Column(Integer, nullable=False, default=0)
    blocked_count = Column(Integer, nullable=False, default=0)
    allowed_count = Column(Integer, nullable=False, default=0)
    redacted_count = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "date", name="uq_api_usage_tenant_date"),
    )
