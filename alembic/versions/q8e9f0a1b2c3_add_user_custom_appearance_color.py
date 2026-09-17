"""Store a custom appearance accent color.

Revision ID: q8e9f0a1b2c3
Revises: p7d8e9f0a1b2
"""

from alembic import op
import sqlalchemy as sa

revision = "q8e9f0a1b2c3"
down_revision = "p7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("appearance_custom_color", sa.String(7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "appearance_custom_color")
