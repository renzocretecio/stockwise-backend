"""add inventory briefings

Revision ID: d4a8f31c920b
Revises: c93d071e5b24
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a8f31c920b"
down_revision = "c93d071e5b24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "inventory_briefings" not in inspector.get_table_names():
        op.create_table(
        "inventory_briefings",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("briefing_date", sa.Date(), nullable=False), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("headline", sa.String(200), nullable=False), sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("narrator_provider", sa.String(30), nullable=False), sa.Column("narrator_model", sa.String(100)),
        sa.Column("metrics_version", sa.String(30), nullable=False), sa.Column("error_message", sa.Text()),
        sa.Column("generated_by", sa.UUID()), sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "briefing_date", name="uq_inventory_briefing_business_date"),
        )
        op.create_index("ix_inventory_briefings_business_date", "inventory_briefings", ["business_id", "briefing_date"])
    if "inventory_recommendations" not in inspector.get_table_names():
        op.create_table(
        "inventory_recommendations",
        sa.Column("id", sa.UUID(), nullable=False), sa.Column("briefing_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID()), sa.Column("purchase_id", sa.UUID()),
        sa.Column("recommendation_type", sa.String(50), nullable=False), sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("priority_score", sa.Integer(), nullable=False), sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False), sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("rule_id", sa.String(50), nullable=False), sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["briefing_id"], ["inventory_briefings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_id"], ["purchases.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_inventory_recommendations_briefing_priority", "inventory_recommendations", ["briefing_id", "priority_score"])


def downgrade() -> None:
    op.drop_index("ix_inventory_recommendations_briefing_priority", table_name="inventory_recommendations")
    op.drop_table("inventory_recommendations")
    op.drop_index("ix_inventory_briefings_business_date", table_name="inventory_briefings")
    op.drop_table("inventory_briefings")
