"""add product supplier purchasing options

Revision ID: j1e2f3a4b5c6
Revises: i0d1e2f3a4b5
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "j1e2f3a4b5c6"
down_revision = "i0d1e2f3a4b5"
branch_labels = None
depends_on = None


def _create_product_suppliers_table() -> None:
    op.create_table(
        "product_suppliers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "supplier_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("supplier_sku", sa.String(length=100), nullable=True),
        sa.Column(
            "unit_cost",
            sa.Numeric(precision=14, scale=2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "lead_time_days",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
        sa.Column(
            "minimum_order_quantity",
            sa.Numeric(precision=14, scale=3),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "pack_size",
            sa.Numeric(precision=14, scale=3),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "is_preferred",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "unit_cost >= 0",
            name="ck_product_suppliers_unit_cost",
        ),
        sa.CheckConstraint(
            "lead_time_days >= 1",
            name="ck_product_suppliers_lead_time_days",
        ),
        sa.CheckConstraint(
            "minimum_order_quantity > 0",
            name="ck_product_suppliers_minimum_order_quantity",
        ),
        sa.CheckConstraint(
            "pack_size > 0",
            name="ck_product_suppliers_pack_size",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["suppliers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "supplier_id",
            name="uq_product_suppliers_product_supplier",
        ),
    )
    op.create_index(
        "ix_product_suppliers_business_id",
        "product_suppliers",
        ["business_id"],
    )
    op.create_index(
        "ix_product_suppliers_product_id",
        "product_suppliers",
        ["product_id"],
    )
    op.create_index(
        "ix_product_suppliers_supplier_id",
        "product_suppliers",
        ["supplier_id"],
    )
    op.create_index(
        "uq_product_suppliers_preferred",
        "product_suppliers",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("is_preferred"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("product_suppliers"):
        _create_product_suppliers_table()
    else:
        existing_indexes = {
            index["name"]
            for index in inspector.get_indexes("product_suppliers")
        }
        indexes = (
            (
                "ix_product_suppliers_business_id",
                ["business_id"],
                False,
                None,
            ),
            (
                "ix_product_suppliers_product_id",
                ["product_id"],
                False,
                None,
            ),
            (
                "ix_product_suppliers_supplier_id",
                ["supplier_id"],
                False,
                None,
            ),
            (
                "uq_product_suppliers_preferred",
                ["product_id"],
                True,
                sa.text("is_preferred"),
            ),
        )
        for name, columns, unique, where_clause in indexes:
            if name not in existing_indexes:
                op.create_index(
                    name,
                    "product_suppliers",
                    columns,
                    unique=unique,
                    postgresql_where=where_clause,
                )

    # Preserve the current primary supplier relationship as the first
    # purchasing option for every existing product.
    op.execute(
        """
        INSERT INTO product_suppliers (
            id,
            business_id,
            product_id,
            supplier_id,
            unit_cost,
            lead_time_days,
            minimum_order_quantity,
            pack_size,
            is_preferred,
            is_active,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            p.business_id,
            p.id,
            p.supplier_id,
            p.cost_price,
            p.lead_time_days,
            1,
            1,
            TRUE,
            TRUE,
            now(),
            now()
        FROM products p
        JOIN suppliers s
          ON s.id = p.supplier_id
         AND s.business_id = p.business_id
        WHERE p.supplier_id IS NOT NULL
        ON CONFLICT (product_id, supplier_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_product_suppliers_preferred",
        table_name="product_suppliers",
    )
    op.drop_index(
        "ix_product_suppliers_supplier_id",
        table_name="product_suppliers",
    )
    op.drop_index(
        "ix_product_suppliers_product_id",
        table_name="product_suppliers",
    )
    op.drop_index(
        "ix_product_suppliers_business_id",
        table_name="product_suppliers",
    )
    op.drop_table("product_suppliers")
