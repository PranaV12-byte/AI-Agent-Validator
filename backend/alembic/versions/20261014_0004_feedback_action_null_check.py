"""Require an expected action for incorrect decision feedback.

Revision ID: 20261014_0004_feedback_check
Revises: 20261013_0003_test_lab_feedback
Create Date: 2026-10-14
"""

from alembic import op


revision = "20261014_0004_feedback_check"
down_revision = "20261013_0003_test_lab_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_decision_feedback_expected_action",
        "decision_feedback",
        type_="check",
    )
    op.create_check_constraint(
        "ck_decision_feedback_expected_action",
        "decision_feedback",
        "(decision = 'incorrect' AND expected_action IS NOT NULL "
        "AND expected_action IN ('allow', 'redact', 'block')) "
        "OR (decision <> 'incorrect' AND expected_action IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_decision_feedback_expected_action",
        "decision_feedback",
        type_="check",
    )
    op.create_check_constraint(
        "ck_decision_feedback_expected_action",
        "decision_feedback",
        "(decision = 'incorrect' AND expected_action IN ('allow', 'redact', 'block')) "
        "OR (decision <> 'incorrect' AND expected_action IS NULL)",
    )
