"""add weekly owner summary settings

Revision ID: aa12bc34de56
Revises: a2b3c4d5e6f7
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = "aa12bc34de56"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "weekly_owner_summary_settings" not in inspector.get_table_names():
        op.create_table(
            "weekly_owner_summary_settings",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("business_id", sa.UUID(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("send_weekday", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("send_hour", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("send_minute", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("recipients", sa.JSON(), nullable=False),
            sa.Column("included_sections", sa.JSON(), nullable=False),
            sa.Column("action_required_only", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_sent_period_end", sa.String(10), nullable=True),
            sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("business_id", name="uq_weekly_owner_summary_business"),
        )
    if "ix_weekly_owner_summary_settings_business_id" not in {
        index["name"] for index in inspector.get_indexes("weekly_owner_summary_settings")
    }:
        op.create_index(
            "ix_weekly_owner_summary_settings_business_id",
            "weekly_owner_summary_settings",
            ["business_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "weekly_owner_summary_settings" in inspector.get_table_names():
        if "ix_weekly_owner_summary_settings_business_id" in {
            index["name"] for index in inspector.get_indexes("weekly_owner_summary_settings")
        }:
            op.drop_index(
                "ix_weekly_owner_summary_settings_business_id",
                table_name="weekly_owner_summary_settings",
            )
        op.drop_table("weekly_owner_summary_settings")