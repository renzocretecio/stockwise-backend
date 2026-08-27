"""add sale void reason

Revision ID: 91c6e3d4a820
Revises: 7b4c2a1f9d10
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "91c6e3d4a820"
down_revision = "7b4c2a1f9d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("void_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales", "void_reason")
