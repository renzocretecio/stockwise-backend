"""add business subscriptions and usage

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = inspector.get_table_names()

    if "business_subscriptions" not in existing_tables:
        op.create_table(
            "business_subscriptions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("business_id", sa.UUID(), nullable=False),
            sa.Column(
                "plan",
                sa.String(length=32),
                server_default="free",
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                server_default="active",
                nullable=False,
            ),
            sa.Column(
                "provider",
                sa.String(length=32),
                server_default="manual",
                nullable=False,
            ),
            sa.Column("provider_customer_id", sa.String(length=255)),
            sa.Column("provider_subscription_id", sa.String(length=255)),
            sa.Column("current_period_ends_at", sa.DateTime(timezone=True)),
            sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
            sa.Column(
                "cancel_at_period_end",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
            sa.Column("cancelled_at", sa.DateTime(timezone=True)),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "business_id",
                name="uq_business_subscriptions_business",
            ),
            sa.UniqueConstraint("provider_subscription_id"),
        )
        op.create_index(
            "ix_business_subscriptions_business_id",
            "business_subscriptions",
            ["business_id"],
        )

    if "subscription_usage" not in existing_tables:
        op.create_table(
            "subscription_usage",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("business_id", sa.UUID(), nullable=False),
            sa.Column("metric", sa.String(length=64), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column(
                "quantity",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "business_id",
                "metric",
                "period_start",
                name="uq_subscription_usage_business_metric_period",
            ),
        )
        op.create_index(
            "ix_subscription_usage_business_id",
            "subscription_usage",
            ["business_id"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = inspector.get_table_names()

    if "subscription_usage" in existing_tables:
        op.drop_index(
            "ix_subscription_usage_business_id",
            table_name="subscription_usage",
        )
        op.drop_table("subscription_usage")

    if "business_subscriptions" in existing_tables:
        op.drop_index(
            "ix_business_subscriptions_business_id",
            table_name="business_subscriptions",
        )
        op.drop_table("business_subscriptions")
