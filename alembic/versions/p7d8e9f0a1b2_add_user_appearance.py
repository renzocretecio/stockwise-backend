"""Store per-user appearance preferences.

Revision ID: p7d8e9f0a1b2
Revises: o6c7d8e9f0a1
"""

from alembic import op
import sqlalchemy as sa

revision = "p7d8e9f0a1b2"
down_revision = "o6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "appearance_palette", sa.String(20),
        nullable=False, server_default="petrol",
    ))
    op.add_column("users", sa.Column(
        "appearance_mode", sa.String(10),
        nullable=False, server_default="system",
    ))


def downgrade() -> None:
    op.drop_column("users", "appearance_mode")
    op.drop_column("users", "appearance_palette")
