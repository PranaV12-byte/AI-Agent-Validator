"""
Tenant model — represents a Safebot business customer.

Each tenant has:
  - Credentials (email + bcrypt password hash)
  - An API key for SDK authentication (sk-... prefix)
  - One-to-many: policies, audit_logs
  - One-to-one:  safety_config
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Tenant(Base):
    """
    Corresponds to the `tenants` table.

    Relationships are lazy-loaded by default; use `selectinload` / `joinedload`
    in queries that need related objects to avoid N+1 queries.
    """

    __tablename__ = "tenants"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_name = Column(String(255), nullable=False)
    email = Column(String(320), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: secrets.token_hex(32),
    )
    # First 8 chars of api_key for safe display: "sk-a3f2..."
    api_key_prefix = Column(String(8), nullable=False)
    active_policy_version = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
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
    policies = relationship(
        "Policy",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    audit_logs = relationship(
        "AuditLog",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    safety_config = relationship(
        "SafetyConfig",
        back_populates="tenant",
        uselist=False,
        cascade="all, delete-orphan",
    )
