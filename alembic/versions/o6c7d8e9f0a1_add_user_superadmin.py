"""add platform superadmin flag to users

Revision ID: o6c7d8e9f0a1
Revises: n5b6c7d8e9f0
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "o6c7d8e9f0a1"
down_revision = "n5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_superadmin" not in user_columns:
        op.add_column(
            "users",
            sa.Column(
                "is_superadmin",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "is_superadmin" in user_columns:
        op.drop_column("users", "is_superadmin")
