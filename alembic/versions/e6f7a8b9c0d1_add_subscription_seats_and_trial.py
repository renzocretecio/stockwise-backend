"""add subscription seats and trial tracking

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("business_subscriptions")
    }

    if "additional_member_seats" not in columns:
        op.add_column(
            "business_subscriptions",
            sa.Column(
                "additional_member_seats",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
        )
    if "trial_started_at" not in columns:
        op.add_column(
            "business_subscriptions",
            sa.Column(
                "trial_started_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("business_subscriptions")
    }

    if "trial_started_at" in columns:
        op.drop_column("business_subscriptions", "trial_started_at")
    if "additional_member_seats" in columns:
        op.drop_column("business_subscriptions", "additional_member_seats")
