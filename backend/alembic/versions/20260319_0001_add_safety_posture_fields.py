"""add safety posture fields

Revision ID: 20260319_0001
Revises:
Create Date: 2026-03-19 18:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260319_0001"
down_revision = "0000_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "safety_configs",
        sa.Column("global_block_enabled", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "safety_configs",
        sa.Column("log_retention_days", sa.Integer(), nullable=True),
    )

    op.execute(
        "UPDATE safety_configs SET global_block_enabled = false WHERE global_block_enabled IS NULL"
    )
    op.execute(
        "UPDATE safety_configs SET log_retention_days = 30 WHERE log_retention_days IS NULL"
    )

    op.alter_column("safety_configs", "global_block_enabled", nullable=False)
    op.alter_column("safety_configs", "log_retention_days", nullable=False)


def downgrade() -> None:
    op.drop_column("safety_configs", "log_retention_days")
    op.drop_column("safety_configs", "global_block_enabled")
