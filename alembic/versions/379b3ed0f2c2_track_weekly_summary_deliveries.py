"""track weekly summary deliveries

Revision ID: 379b3ed0f2c2
Revises: e5b4e733f2ab
Create Date: 2026-09-20 13:40:57.802598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "379b3ed0f2c2"
down_revision: Union[str, None] = "e5b4e733f2ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column("last_attempt_period_end", sa.String(10)),
    )
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column("last_attempted_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column("last_delivery_status", sa.String(20)),
    )
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column("last_delivery_error", sa.Text()),
    )
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "weekly_owner_summary_settings",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_column("weekly_owner_summary_settings", "next_attempt_at")
    op.drop_column("weekly_owner_summary_settings", "consecutive_failures")
    op.drop_column("weekly_owner_summary_settings", "last_delivery_error")
    op.drop_column("weekly_owner_summary_settings", "last_delivery_status")
    op.drop_column("weekly_owner_summary_settings", "last_sent_at")
    op.drop_column("weekly_owner_summary_settings", "last_attempted_at")
    op.drop_column("weekly_owner_summary_settings", "last_attempt_period_end")
