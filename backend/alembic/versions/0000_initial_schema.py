"""initial schema — create all tables from scratch

Revision ID: 0000_initial_schema
Revises:
Create Date: 2026-03-24

This migration creates the full database schema from scratch.
It uses IF NOT EXISTS guards so it is safe to run against an
existing database that was bootstrapped manually.

Existing installs at revision 91d725d72296 can upgrade cleanly:
    alembic upgrade head
Only the new 'add_perf_indexes' migration will be applied since
Alembic tracks from the stored current revision.
"""

from alembic import op

revision = "0000_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector extension is required for policy_embeddings.embedding
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_name VARCHAR(255) NOT NULL,
            email VARCHAR(320) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            api_key VARCHAR(64) NOT NULL,
            api_key_prefix VARCHAR(8) NOT NULL,
            active_policy_version INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenants_email UNIQUE (email),
            CONSTRAINT uq_tenants_api_key UNIQUE (api_key)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenants_email ON tenants (email)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tenants_api_key ON tenants (api_key)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS safety_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            injection_protection BOOLEAN NOT NULL DEFAULT TRUE,
            injection_sensitivity VARCHAR(20) NOT NULL DEFAULT 'moderate',
            pii_redaction BOOLEAN NOT NULL DEFAULT TRUE,
            pii_types JSONB NOT NULL DEFAULT '["aadhaar","pan","email","phone","upi"]'::jsonb,
            global_block_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            policy_enforcement BOOLEAN NOT NULL DEFAULT TRUE,
            fail_mode VARCHAR(20) NOT NULL DEFAULT 'closed',
            fallback_message TEXT NOT NULL DEFAULT
                'I cannot help with that request. A human agent will follow up.',
            log_retention_days INTEGER NOT NULL DEFAULT 30,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_safety_configs_tenant_id UNIQUE (tenant_id),
            CONSTRAINT fk_safety_configs_tenant FOREIGN KEY (tenant_id)
                REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS policies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            rule_text TEXT NOT NULL,
            rule_type VARCHAR(50) NOT NULL DEFAULT 'semantic',
            parameters JSONB DEFAULT '{}'::jsonb,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            version INTEGER NOT NULL DEFAULT 1,
            policy_hash VARCHAR(64),
            algorand_tx_id VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_policies_tenant FOREIGN KEY (tenant_id)
                REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_policies_tenant_id ON policies (tenant_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            policy_id UUID NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding vector(384) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_pe_tenant FOREIGN KEY (tenant_id)
                REFERENCES tenants(id) ON DELETE CASCADE,
            CONSTRAINT fk_pe_policy FOREIGN KEY (policy_id)
                REFERENCES policies(id) ON DELETE CASCADE
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pe_tenant_id ON policy_embeddings (tenant_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            session_id VARCHAR(64),
            hook_type VARCHAR(20) NOT NULL,
            action VARCHAR(20) NOT NULL,
            violation_type VARCHAR(50),
            severity VARCHAR(10) NOT NULL DEFAULT 'medium',
            input_preview TEXT,
            details JSONB DEFAULT '{}'::jsonb,
            payload_hash VARCHAR(64),
            policy_version INTEGER,
            algorand_tx_id VARCHAR(64),
            processing_ms INTEGER,
            ip_address INET,
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_audit_logs_tenant FOREIGN KEY (tenant_id)
                REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            date DATE NOT NULL DEFAULT CURRENT_DATE,
            total_requests INTEGER NOT NULL DEFAULT 0,
            blocked_count INTEGER NOT NULL DEFAULT 0,
            allowed_count INTEGER NOT NULL DEFAULT 0,
            redacted_count INTEGER NOT NULL DEFAULT 0,
            avg_latency_ms FLOAT DEFAULT 0.0,
            CONSTRAINT uq_api_usage_tenant_date UNIQUE (tenant_id, date),
            CONSTRAINT fk_api_usage_tenant FOREIGN KEY (tenant_id)
                REFERENCES tenants(id) ON DELETE CASCADE
        )
    """)


def downgrade() -> None:
    import os
    if os.environ.get("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError(
            "Refusing to run initial schema downgrade in production — "
            "this would DROP ALL TABLES. Set ENVIRONMENT to a non-production "
            "value if you truly intend to destroy all data."
        )
    op.execute("DROP TABLE IF EXISTS api_usage")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS policy_embeddings")
    op.execute("DROP TABLE IF EXISTS policies")
    op.execute("DROP TABLE IF EXISTS safety_configs")
    op.execute("DROP TABLE IF EXISTS tenants")
