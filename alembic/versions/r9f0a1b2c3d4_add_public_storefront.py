"""Add public storefronts and online order requests.

Revision ID: r9f0a1b2c3d4
Revises: 379b3ed0f2c2
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "r9f0a1b2c3d4"
down_revision = "379b3ed0f2c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "public_stores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(150), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("logo_url", sa.Text()),
        sa.Column("banner_url", sa.Text()),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "out_of_stock_behavior",
            sa.String(30),
            nullable=False,
            server_default="mark_sold_out",
        ),
        sa.Column(
            "pickup_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "delivery_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "payment_methods",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column(
            "payment_instructions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "out_of_stock_behavior IN " "('mark_sold_out', 'hide', 'continue_selling')",
            name="ck_public_stores_stock_behavior",
        ),
        sa.UniqueConstraint(
            "business_id",
            name="uq_public_stores_business_id",
        ),
        sa.UniqueConstraint("slug", name="uq_public_stores_slug"),
    )
    op.create_index(
        "ix_public_stores_business_id",
        "public_stores",
        ["business_id"],
    )
    op.create_index(
        "ix_public_stores_slug",
        "public_stores",
        ["slug"],
    )

    op.create_table(
        "store_products",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public_stores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("public_name", sa.String(200)),
        sa.Column("public_description", sa.Text()),
        sa.Column("public_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("public_image_url", sa.Text()),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "public_price >= 0",
            name="ck_store_products_public_price",
        ),
        sa.UniqueConstraint(
            "store_id",
            "product_id",
            name="uq_store_products_store_product",
        ),
    )
    op.create_index(
        "ix_store_products_store_id",
        "store_products",
        ["store_id"],
    )
    op.create_index(
        "ix_store_products_product_id",
        "store_products",
        ["product_id"],
    )

    op.create_table(
        "store_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "store_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("public_stores.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "business_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("businesses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="SET NULL"),
        ),
        sa.Column("reference_number", sa.String(100), nullable=False),
        sa.Column("tracking_token", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="new",
        ),
        sa.Column("customer_name", sa.String(150), nullable=False),
        sa.Column("customer_contact", sa.String(100), nullable=False),
        sa.Column("delivery_method", sa.String(20), nullable=False),
        sa.Column("delivery_address", sa.Text()),
        sa.Column("customer_notes", sa.Text()),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column(
            "subtotal",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "completed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "cancelled_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("processing_at", sa.DateTime(timezone=True)),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.Column("shipped_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancellation_reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'confirmed', 'processing', 'ready', "
            "'shipped', 'completed', 'cancelled')",
            name="ck_store_orders_status",
        ),
        sa.CheckConstraint(
            "delivery_method IN ('pickup', 'delivery')",
            name="ck_store_orders_delivery_method",
        ),
        sa.UniqueConstraint(
            "business_id",
            "reference_number",
            name="uq_store_orders_business_reference",
        ),
        sa.UniqueConstraint("sale_id", name="uq_store_orders_sale_id"),
        sa.UniqueConstraint(
            "tracking_token",
            name="uq_store_orders_tracking_token",
        ),
    )
    op.create_index(
        "ix_store_orders_store_id",
        "store_orders",
        ["store_id"],
    )
    op.create_index(
        "ix_store_orders_business_id",
        "store_orders",
        ["business_id"],
    )
    op.create_index(
        "ix_store_orders_tracking_token",
        "store_orders",
        ["tracking_token"],
    )
    op.create_index(
        "ix_store_orders_business_status_created",
        "store_orders",
        ["business_id", "status", "created_at"],
    )

    op.create_table(
        "store_order_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("store_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(100)),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column(
            "reserved_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "unit_cost",
            sa.Numeric(14, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_store_order_items_quantity",
        ),
        sa.CheckConstraint(
            "reserved_quantity >= 0 AND reserved_quantity <= quantity",
            name="ck_store_order_items_reserved_quantity",
        ),
        sa.UniqueConstraint(
            "order_id",
            "product_id",
            name="uq_store_order_items_order_product",
        ),
    )
    op.create_index(
        "ix_store_order_items_order_id",
        "store_order_items",
        ["order_id"],
    )
    op.create_index(
        "ix_store_order_items_product_id",
        "store_order_items",
        ["product_id"],
    )

    permissions = {
        "storefront.read": "View public store settings and customer orders",
        "storefront.manage": ("Manage the public store and published products"),
        "storefront.orders": "Confirm and fulfill public store orders",
    }
    for key, description in permissions.items():
        op.execute(
            sa.text(
                """
                INSERT INTO permissions (id, key, description)
                VALUES (gen_random_uuid(), :key, :description)
                ON CONFLICT (key) DO UPDATE
                SET description = EXCLUDED.description
                """
            ).bindparams(key=key, description=description)
        )

    role_permissions = {
        "owner": list(permissions),
        "manager": list(permissions),
        "cashier": ["storefront.read", "storefront.orders"],
        "stock clerk": ["storefront.read"],
    }
    for role_name, permission_keys in role_permissions.items():
        for permission_key in permission_keys:
            op.execute(
                sa.text(
                    """
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id
                    FROM roles r
                    JOIN permissions p ON p.key = :permission_key
                    WHERE lower(r.name) = :role_name
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                    """
                ).bindparams(
                    role_name=role_name,
                    permission_key=permission_key,
                )
            )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions
                WHERE key IN (
                    'storefront.read',
                    'storefront.manage',
                    'storefront.orders'
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE key IN (
                'storefront.read',
                'storefront.manage',
                'storefront.orders'
            )
            """
        )
    )
    op.drop_table("store_order_items")
    op.drop_table("store_orders")
    op.drop_table("store_products")
    op.drop_table("public_stores")
