"""add manual payment submission fields

Revision ID: n5b6c7d8e9f0
Revises: m4a5b6c7d8e9
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "n5b6c7d8e9f0"
down_revision = "m4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"]
        for column in inspector.get_columns("subscription_upgrade_requests")
    }
    if "payment_method" not in columns:
        op.add_column(
            "subscription_upgrade_requests",
            sa.Column("payment_method", sa.String(length=64), nullable=True),
        )
    if "payment_submitted_at" not in columns:
        op.add_column(
            "subscription_upgrade_requests",
            sa.Column("payment_submitted_at", sa.DateTime(timezone=True)),
        )
    subscription_columns = {
        column["name"] for column in inspector.get_columns("business_subscriptions")
    }
    if "current_period_started_at" not in subscription_columns:
        op.add_column(
            "business_subscriptions",
            sa.Column("current_period_started_at", sa.DateTime(timezone=True)),
        )

    indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(
            "subscription_upgrade_requests"
        )
    }
    if "uq_subscription_upgrade_requests_pending_business" in indexes:
        op.drop_index(
            "uq_subscription_upgrade_requests_pending_business",
            table_name="subscription_upgrade_requests",
        )
    if "uq_subscription_upgrade_requests_active_business" not in indexes:
        op.create_index(
            "uq_subscription_upgrade_requests_active_business",
            "subscription_upgrade_requests",
            ["business_id"],
            unique=True,
            postgresql_where=sa.text(
                "status IN ('pending', 'awaiting_payment', 'payment_submitted')"
            ),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    indexes = {
        index["name"]
        for index in inspector.get_indexes("subscription_upgrade_requests")
    }
    if "uq_subscription_upgrade_requests_active_business" in indexes:
        op.drop_index(
            "uq_subscription_upgrade_requests_active_business",
            table_name="subscription_upgrade_requests",
        )
    if "uq_subscription_upgrade_requests_pending_business" not in indexes:
        op.create_index(
            "uq_subscription_upgrade_requests_pending_business",
            "subscription_upgrade_requests",
            ["business_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )

    columns = {
        column["name"]
        for column in inspector.get_columns("subscription_upgrade_requests")
    }
    if "payment_submitted_at" in columns:
        op.drop_column("subscription_upgrade_requests", "payment_submitted_at")
    if "payment_method" in columns:
        op.drop_column("subscription_upgrade_requests", "payment_method")

    subscription_columns = {
        column["name"] for column in inspector.get_columns("business_subscriptions")
    }
    if "current_period_started_at" in subscription_columns:
        op.drop_column("business_subscriptions", "current_period_started_at")
