"""add manual subscription upgrade requests

Revision ID: m4a5b6c7d8e9
Revises: l3f4a5b6c7d8
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "m4a5b6c7d8e9"
down_revision = "l3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    subscription_columns = {
        column["name"] for column in inspector.get_columns("business_subscriptions")
    }
    if "billing_interval" not in subscription_columns:
        op.add_column(
            "business_subscriptions",
            sa.Column(
                "billing_interval",
                sa.String(length=16),
                server_default="monthly",
                nullable=False,
            ),
        )

    if not inspector.has_table("subscription_upgrade_requests"):
        op.create_table(
            "subscription_upgrade_requests",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("business_id", sa.UUID(), nullable=False),
            sa.Column("requested_by", sa.UUID(), nullable=True),
            sa.Column("requested_plan", sa.String(length=32), nullable=False),
            sa.Column(
                "requested_billing_interval",
                sa.String(length=16),
                nullable=False,
            ),
            sa.Column(
                "requested_additional_member_seats",
                sa.Integer(),
                server_default="0",
                nullable=False,
            ),
            sa.Column("quoted_amount_php", sa.Integer(), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                server_default="pending",
                nullable=False,
            ),
            sa.Column("payment_reference", sa.String(length=255)),
            sa.Column("admin_note", sa.String(length=500)),
            sa.Column("approved_plan", sa.String(length=32)),
            sa.Column("approved_billing_interval", sa.String(length=16)),
            sa.Column("approved_additional_member_seats", sa.Integer()),
            sa.Column("approved_amount_php", sa.Integer()),
            sa.Column("reviewed_by", sa.UUID(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
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
            sa.ForeignKeyConstraint(
                ["requested_by"],
                ["users.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["reviewed_by"],
                ["users.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(
            "subscription_upgrade_requests"
        )
    }
    if "ix_subscription_upgrade_requests_business_id" not in existing_indexes:
        op.create_index(
            "ix_subscription_upgrade_requests_business_id",
            "subscription_upgrade_requests",
            ["business_id"],
        )
    if "ix_subscription_upgrade_requests_status" not in existing_indexes:
        op.create_index(
            "ix_subscription_upgrade_requests_status",
            "subscription_upgrade_requests",
            ["status"],
        )
    if "uq_subscription_upgrade_requests_pending_business" not in existing_indexes:
        op.create_index(
            "uq_subscription_upgrade_requests_pending_business",
            "subscription_upgrade_requests",
            ["business_id"],
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("subscription_upgrade_requests"):
        op.drop_index(
            "uq_subscription_upgrade_requests_pending_business",
            table_name="subscription_upgrade_requests",
        )
        op.drop_index(
            "ix_subscription_upgrade_requests_status",
            table_name="subscription_upgrade_requests",
        )
        op.drop_index(
            "ix_subscription_upgrade_requests_business_id",
            table_name="subscription_upgrade_requests",
        )
        op.drop_table("subscription_upgrade_requests")

    subscription_columns = {
        column["name"] for column in inspector.get_columns("business_subscriptions")
    }
    if "billing_interval" in subscription_columns:
        op.drop_column("business_subscriptions", "billing_interval")
