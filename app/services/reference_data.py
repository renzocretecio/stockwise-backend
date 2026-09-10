from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.inventory import StockBalance
from app.models.product import Product, ProductSupplier, Supplier


class ReferenceDataService:
    """Build the compact, business-scoped catalog used by forms."""

    @staticmethod
    def get_catalog(
        business_id: str,
        db: Session,
        include_suppliers: bool,
        include_stock: bool,
    ) -> dict:
        products = db.execute(
            select(Product)
            .where(
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
            .order_by(Product.name)
        ).scalars().all()

        categories = db.execute(
            select(Category)
            .where(
                Category.business_id == business_id,
                Category.is_active.is_(True),
            )
            .order_by(Category.name)
        ).scalars().all()

        suppliers = []
        supplier_products = []
        if include_suppliers:
            suppliers = db.execute(
                select(Supplier)
                .where(
                    Supplier.business_id == business_id,
                    Supplier.is_active.is_(True),
                )
                .order_by(Supplier.name)
            ).scalars().all()
            supplier_products = db.execute(
                select(ProductSupplier)
                .join(Product, Product.id == ProductSupplier.product_id)
                .join(
                    Supplier,
                    Supplier.id == ProductSupplier.supplier_id,
                )
                .where(
                    ProductSupplier.business_id == business_id,
                    ProductSupplier.is_active.is_(True),
                    Product.business_id == business_id,
                    Product.is_active.is_(True),
                    Supplier.business_id == business_id,
                    Supplier.is_active.is_(True),
                )
                .order_by(
                    ProductSupplier.supplier_id,
                    ProductSupplier.product_id,
                )
            ).scalars().all()

        stock_balances = []
        if include_stock:
            stock_balances = db.execute(
                select(StockBalance)
                .join(Product, Product.id == StockBalance.product_id)
                .where(
                    StockBalance.business_id == business_id,
                    Product.business_id == business_id,
                    Product.is_active.is_(True),
                )
                .order_by(StockBalance.product_id)
            ).scalars().all()

        return {
            "success": True,
            "business_id": business_id,
            "generated_at": datetime.now(timezone.utc),
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "sku": product.sku,
                    "barcode": product.barcode,
                    "supplier_id": product.supplier_id,
                    "category_id": product.category_id,
                    "cost_price": product.cost_price,
                    "selling_price": product.selling_price,
                    "unit": product.unit,
                    "reorder_point": product.reorder_point,
                    "safety_stock": product.safety_stock,
                    "lead_time_days": product.lead_time_days,
                    "is_perishable": product.is_perishable,
                    "updated_at": product.updated_at,
                }
                for product in products
            ],
            "suppliers": [
                {
                    "id": supplier.id,
                    "name": supplier.name,
                    "lead_time_days": supplier.lead_time_days,
                    "updated_at": supplier.updated_at,
                }
                for supplier in suppliers
            ],
            "supplier_products": [
                {
                    "product_id": item.product_id,
                    "supplier_id": item.supplier_id,
                    "supplier_sku": item.supplier_sku,
                    "unit_cost": item.unit_cost,
                    "lead_time_days": item.lead_time_days,
                    "minimum_order_quantity": (
                        item.minimum_order_quantity
                    ),
                    "pack_size": item.pack_size,
                    "is_preferred": item.is_preferred,
                    "updated_at": item.updated_at,
                }
                for item in supplier_products
            ],
            "categories": [
                {
                    "id": category.id,
                    "name": category.name,
                    "updated_at": category.updated_at,
                }
                for category in categories
            ],
            "stock_balances": [
                {
                    "product_id": balance.product_id,
                    "quantity": balance.quantity,
                    "reserved_quantity": balance.reserved_quantity,
                    "average_cost": balance.average_cost,
                    "updated_at": balance.updated_at,
                }
                for balance in stock_balances
            ],
        }
