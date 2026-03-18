"""
PolicyEmbedding model — stores vector embeddings for policy rules.

Each policy may have one or more embedding chunks stored here.
The embedding column uses pgvector's Vector(384) type, matching
the output dimension of all-MiniLM-L6-v2 (SentenceTransformers).

IVFFlat index should be created AFTER initial data load (see schema comment):
    CREATE INDEX idx_pe_vector ON policy_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from pgvector.sqlalchemy import Vector

from app.database import Base


class PolicyEmbedding(Base):
    """Corresponds to the `policy_embeddings` table."""

    __tablename__ = "policy_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_text = Column(Text, nullable=False)
    # 384-dimensional vector — all-MiniLM-L6-v2 output size
    embedding = Column(Vector(384), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    policy = relationship("Policy", back_populates="embeddings")
