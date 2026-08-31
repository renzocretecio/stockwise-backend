"""add business onboarding fields

Revision ID: f1a2b3c4d5e6
Revises: d4a8f31c920b
Create Date: 2026-08-31
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "d4a8f31c920b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "businesses",
        sa.Column("industry", sa.String(100), nullable=True),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "businesses",
        sa.Column(
            "onboarding_completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.alter_column(
        "businesses",
        "onboarding_completed",
        server_default=sa.false(),
    )


def downgrade() -> None:
    op.drop_column("businesses", "onboarding_completed_at")
    op.drop_column("businesses", "onboarding_completed")
    op.drop_column("businesses", "industry")
