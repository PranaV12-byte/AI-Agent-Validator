"""Add email_verified to tenants; add email verification token support

Revision ID: add_email_verification
Revises: add_perf_indexes
Create Date: 2026-04-05

All existing tenants are migrated to email_verified=True — they pre-date the
feature and we do not want to lock out active users on upgrade.
New signups in production will start as email_verified=False until the user
clicks the verification link sent to their inbox.
"""

from alembic import op
import sqlalchemy as sa

revision = "add_email_verification"
down_revision = "add_perf_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("email_verified", sa.Boolean(), nullable=True),
    )
    # Back-fill: existing tenants are considered verified
    op.execute("UPDATE tenants SET email_verified = true WHERE email_verified IS NULL")
    op.alter_column("tenants", "email_verified", nullable=False)


def downgrade() -> None:
    op.drop_column("tenants", "email_verified")
