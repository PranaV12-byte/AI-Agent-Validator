"""add performance indexes — audit_logs and vector similarity

Revision ID: add_perf_indexes
Revises: 91d725d72296
Create Date: 2026-03-24

Adds indexes on the two most performance-critical tables:
  - audit_logs: tenant_id, created_at (DESC), action, composite tenant+time
  - policy_embeddings: IVFFlat cosine index for pgvector similarity search

The IVFFlat index requires the vector extension (created in 0000_initial_schema).
lists=100 is appropriate up to ~1M embedding rows; tune upward beyond that.
"""

from alembic import op

revision = "add_perf_indexes"
down_revision = "91d725d72296"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Audit log query indexes (dashboard + audit log page)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id
        ON audit_logs (tenant_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at
        ON audit_logs (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_action
        ON audit_logs (action)
    """)
    # Composite: covers the most common query (tenant logs ordered by time)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_created
        ON audit_logs (tenant_id, created_at DESC)
    """)

    # IVFFlat vector index for cosine similarity policy matching
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_pe_embedding_ivfflat
        ON policy_embeddings
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pe_embedding_ivfflat")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_tenant_created")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_action")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_at")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_tenant_id")
