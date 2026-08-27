"""add sale returns

Revision ID: 7b4c2a1f9d10
Revises: e3878d300632
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "7b4c2a1f9d10"
down_revision = "e3878d300632"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "sale_returns" not in inspector.get_table_names():
        op.create_table(
        "sale_returns",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_id", sa.UUID(), nullable=False),
        sa.Column("sale_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="completed"),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('completed', 'cancelled')", name="ck_sale_returns_status"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        )
    else:
        check_names = {check["name"] for check in inspector.get_check_constraints("sale_returns")}
        if "ck_sale_returns_status" not in check_names:
            op.create_check_constraint(
                "ck_sale_returns_status",
                "sale_returns",
                "status IN ('completed', 'cancelled')",
            )

    return_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("sale_returns")}
    if "ix_sale_returns_sale_id" not in return_indexes:
        op.create_index("ix_sale_returns_sale_id", "sale_returns", ["sale_id"])

    inspector = sa.inspect(bind)
    if "sale_return_items" not in inspector.get_table_names():
        op.create_table(
        "sale_return_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("return_id", sa.UUID(), nullable=False),
        sa.Column("sale_item_id", sa.UUID(), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("quantity > 0", name="ck_sale_return_items_quantity_positive"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["return_id"], ["sale_returns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sale_item_id"], ["sale_items.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("return_id", "sale_item_id", name="uq_sale_return_item"),
        )
    else:
        check_names = {check["name"] for check in inspector.get_check_constraints("sale_return_items")}
        if "ck_sale_return_items_quantity_positive" not in check_names:
            op.create_check_constraint(
                "ck_sale_return_items_quantity_positive",
                "sale_return_items",
                "quantity > 0",
            )
        unique_names = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("sale_return_items")
        }
        if "uq_sale_return_item" not in unique_names:
            op.create_unique_constraint(
                "uq_sale_return_item",
                "sale_return_items",
                ["return_id", "sale_item_id"],
            )

    item_indexes = {
        index["name"]
        for index in sa.inspect(bind).get_indexes("sale_return_items")
    }
    if "ix_sale_return_items_sale_item_id" not in item_indexes:
        op.create_index(
            "ix_sale_return_items_sale_item_id",
            "sale_return_items",
            ["sale_item_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_sale_return_items_sale_item_id", table_name="sale_return_items")
    op.drop_table("sale_return_items")
    op.drop_index("ix_sale_returns_sale_id", table_name="sale_returns")
    op.drop_table("sale_returns")
