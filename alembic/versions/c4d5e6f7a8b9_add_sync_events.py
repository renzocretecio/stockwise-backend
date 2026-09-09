"""add durable offline sync events

Revision ID: c4d5e6f7a8b9
Revises: bc23de45fa67
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "bc23de45fa67"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sync_events" in inspector.get_table_names():
        return

    op.create_table(
        "sync_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("client_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "business_id",
            "client_event_id",
            name="uq_sync_events_business_client_event",
        ),
    )
    op.create_index(
        "ix_sync_events_business_created_at",
        "sync_events",
        ["business_id", "created_at"],
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "sync_events" in inspector.get_table_names():
        op.drop_index(
            "ix_sync_events_business_created_at",
            table_name="sync_events",
        )
        op.drop_table("sync_events")