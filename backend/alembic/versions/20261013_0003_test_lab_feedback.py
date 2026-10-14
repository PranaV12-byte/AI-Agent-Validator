"""Add tenant-scoped Test Lab cases and decision feedback.

Revision ID: 20261013_0003_test_lab_feedback
Revises: 20261012_0002_auth_version
Create Date: 2026-10-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20261013_0003_test_lab_feedback"
down_revision = "20261012_0002_auth_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=12), nullable=False),
        sa.Column("expected_action", sa.String(length=8), nullable=True),
        sa.Column(
            "status",
            sa.String(length=8),
            server_default="open",
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IN ('correct', 'incorrect', 'unsure')",
            name="ck_decision_feedback_decision",
        ),
        sa.CheckConstraint(
            "(decision = 'incorrect' AND expected_action IN ('allow', 'redact', 'block')) "
            "OR (decision <> 'incorrect' AND expected_action IS NULL)",
            name="ck_decision_feedback_expected_action",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_decision_feedback_status",
        ),
        sa.CheckConstraint(
            "note IS NULL OR char_length(note) <= 500",
            name="ck_decision_feedback_note_length",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["audit_log_id"], ["audit_logs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_log_id", name="uq_decision_feedback_audit_log_id"),
    )
    op.create_index(
        "ix_decision_feedback_tenant_id",
        "decision_feedback",
        ["tenant_id"],
    )

    op.create_table(
        "test_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("expected_action", sa.String(length=8), nullable=False),
        sa.Column(
            "synthetic_data_acknowledged",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("last_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(name) BETWEEN 1 AND 120",
            name="ck_test_cases_name_length",
        ),
        sa.CheckConstraint(
            "char_length(prompt) BETWEEN 1 AND 4000",
            name="ck_test_cases_prompt_length",
        ),
        sa.CheckConstraint(
            "expected_action IN ('allow', 'redact', 'block')",
            name="ck_test_cases_expected_action",
        ),
        sa.CheckConstraint(
            "synthetic_data_acknowledged IS TRUE",
            name="ck_test_cases_synthetic_acknowledged",
        ),
        sa.CheckConstraint("revision > 0", name="ck_test_cases_revision"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_feedback_id"], ["decision_feedback.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_cases_tenant_id", "test_cases", ["tenant_id"])
    op.create_index(
        "ix_test_cases_source_feedback_id",
        "test_cases",
        ["source_feedback_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_test_cases_source_feedback_id", table_name="test_cases")
    op.drop_index("ix_test_cases_tenant_id", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index(
        "ix_decision_feedback_tenant_id", table_name="decision_feedback"
    )
    op.drop_table("decision_feedback")
