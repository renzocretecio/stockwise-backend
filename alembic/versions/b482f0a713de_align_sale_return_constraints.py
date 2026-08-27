"""align sale return constraints

Revision ID: b482f0a713de
Revises: 91c6e3d4a820
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "b482f0a713de"
down_revision = "91c6e3d4a820"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_sales_status", "sales", type_="check")
    op.create_check_constraint(
        "ck_sales_status",
        "sales",
        "status IN ('draft', 'completed', 'partially_returned', 'returned', 'voided')",
    )

    inspector = sa.inspect(op.get_bind())
    return_item_columns = {
        column["name"] for column in inspector.get_columns("sale_return_items")
    }
    if "restocked" in return_item_columns:
        op.drop_column("sale_return_items", "restocked")


def downgrade() -> None:
    op.add_column(
        "sale_return_items",
        sa.Column("restocked", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_constraint("ck_sales_status", "sales", type_="check")
    op.create_check_constraint(
        "ck_sales_status",
        "sales",
        "status IN ('draft', 'completed', 'voided')",
    )
