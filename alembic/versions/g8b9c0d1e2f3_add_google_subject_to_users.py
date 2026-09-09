"""add Google subject to users

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa


revision = "g8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    if "google_subject" not in columns:
        op.add_column(
            "users",
            sa.Column("google_subject", sa.String(255), nullable=True),
        )

    inspector = sa.inspect(op.get_bind())
    indexes = {
        index["name"] for index in inspector.get_indexes("users")
    }
    if "ix_users_google_subject" not in indexes:
        op.create_index(
            "ix_users_google_subject",
            "users",
            ["google_subject"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {
        index["name"] for index in inspector.get_indexes("users")
    }
    if "ix_users_google_subject" in indexes:
        op.drop_index("ix_users_google_subject", table_name="users")

    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    if "google_subject" in columns:
        op.drop_column("users", "google_subject")
