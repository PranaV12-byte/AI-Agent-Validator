"""Add tenant auth version for immediate session invalidation.

Revision ID: 20261012_0002_auth_version
Revises: add_email_verification
Create Date: 2026-10-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20261012_0002_auth_version"
down_revision = "add_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("tenants", "auth_version")
