"""Saved synthetic test cases and human review of audit decisions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class DecisionFeedback(Base):
    """One tenant-owned review record per immutable audit decision."""

    __tablename__ = "decision_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    audit_log_id = Column(
        UUID(as_uuid=True),
        ForeignKey("audit_logs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    decision = Column(String(12), nullable=False)
    expected_action = Column(String(8))
    status = Column(String(8), nullable=False, default="open", server_default="open")
    note = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN ('correct', 'incorrect', 'unsure')",
            name="ck_decision_feedback_decision",
        ),
        CheckConstraint(
            "(decision = 'incorrect' AND expected_action IS NOT NULL "
            "AND expected_action IN ('allow', 'redact', 'block')) "
            "OR (decision <> 'incorrect' AND expected_action IS NULL)",
            name="ck_decision_feedback_expected_action",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_decision_feedback_status",
        ),
        CheckConstraint(
            "note IS NULL OR char_length(note) <= 500",
            name="ck_decision_feedback_note_length",
        ),
    )

    tenant = relationship("Tenant", back_populates="decision_feedback")


class TestCase(Base):
    """A manually authored synthetic input and its most recent evaluation."""

    __tablename__ = "test_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_feedback_id = Column(
        UUID(as_uuid=True),
        ForeignKey("decision_feedback.id", ondelete="SET NULL"),
        index=True,
    )
    name = Column(String(120), nullable=False)
    prompt = Column(Text, nullable=False)
    expected_action = Column(String(8), nullable=False)
    synthetic_data_acknowledged = Column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    last_result = Column(JSONB)
    last_run_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default="now()",
    )

    __table_args__ = (
        CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120",
            name="ck_test_cases_name_length",
        ),
        CheckConstraint(
            "char_length(prompt) BETWEEN 1 AND 4000",
            name="ck_test_cases_prompt_length",
        ),
        CheckConstraint(
            "expected_action IN ('allow', 'redact', 'block')",
            name="ck_test_cases_expected_action",
        ),
        CheckConstraint(
            "synthetic_data_acknowledged IS TRUE",
            name="ck_test_cases_synthetic_acknowledged",
        ),
        CheckConstraint("revision > 0", name="ck_test_cases_revision"),
    )

    tenant = relationship("Tenant", back_populates="test_cases")
