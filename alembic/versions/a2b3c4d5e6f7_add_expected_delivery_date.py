"""add expected purchase delivery date

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchases",
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_purchases_expected_delivery_date",
        "purchases",
        ["expected_delivery_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchases_expected_delivery_date",
        table_name="purchases",
    )
    op.drop_column("purchases", "expected_delivery_date")
