"""Seed comprehensive development data into an existing business.

Usage:
    PYTHONPATH=. venv/bin/python database/seed_business_demo.py \
        --business-id <uuid> --user-id <uuid>

The script is idempotent. It exits when the marker supplier already exists.
"""

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config.database import SessionLocal
from app.config.settings import settings
from app.models.auth import User
from app.models.briefing import InventoryBriefing
from app.models.business import Business
from app.models.category import Category
from app.models.inventory import (
    InventoryCount,
    InventoryCountItem,
    StockBalance,
    StockMovement,
)
from app.models.membership import BusinessMembership
from app.models.product import Product, Supplier
from app.models.purchase import Purchase, PurchaseItem
from app.models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem
from app.services.briefing import BriefingService


MARKER_SUPPLIER = "Demo Tech Distribution"
DEMO_PREFIX = "DEMO-"


PRODUCTS = [
    {
        "sku": "DEMO-EARBUDS",
        "name": "Wireless Earbuds",
        "category": "Electronics",
        "supplier": "tech",
        "cost": "350",
        "price": "599",
        "stock": "18",
        "reorder": "20",
        "safety": "10",
        "lead": 7,
    },
    {
        "sku": "DEMO-USBC",
        "name": "USB-C Cable",
        "category": "Accessories",
        "supplier": "accessories",
        "cost": "70",
        "price": "149",
        "stock": "22",
        "reorder": "35",
        "safety": "15",
        "lead": 5,
    },
    {
        "sku": "DEMO-CHARGER",
        "name": "20W Fast Charger",
        "category": "Electronics",
        "supplier": "tech",
        "cost": "220",
        "price": "399",
        "stock": "36",
        "reorder": "25",
        "safety": "10",
        "lead": 7,
    },
    {
        "sku": "DEMO-POWERBANK",
        "name": "10000mAh Power Bank",
        "category": "Electronics",
        "supplier": "tech",
        "cost": "480",
        "price": "799",
        "stock": "9",
        "reorder": "15",
        "safety": "6",
        "lead": 10,
    },
    {
        "sku": "DEMO-CASE",
        "name": "Universal Phone Case",
        "category": "Accessories",
        "supplier": "accessories",
        "cost": "300",
        "price": "499",
        "stock": "215",
        "reorder": "20",
        "safety": "5",
        "lead": 5,
    },
    {
        "sku": "DEMO-TABLET",
        "name": "Tablet Cover",
        "category": "Accessories",
        "supplier": "accessories",
        "cost": "260",
        "price": "449",
        "stock": "120",
        "reorder": "15",
        "safety": "5",
        "lead": 5,
    },
    {
        "sku": "DEMO-COFFEE",
        "name": "Organic Coffee Beans",
        "category": "Beverages",
        "supplier": "local",
        "cost": "180",
        "price": "280",
        "stock": "114",
        "reorder": "20",
        "safety": "8",
        "lead": 3,
    },
    {
        "sku": "DEMO-MOUSE",
        "name": "Wireless Mouse",
        "category": "Electronics",
        "supplier": "tech",
        "cost": "250",
        "price": "449",
        "stock": "80",
        "reorder": "15",
        "safety": "5",
        "lead": 7,
    },
    {
        "sku": "DEMO-PROTECTOR",
        "name": "Tempered Glass Screen Protector",
        "category": "Accessories",
        "supplier": "accessories",
        "cost": "45",
        "price": "129",
        "stock": "300",
        "reorder": "30",
        "safety": "10",
        "lead": 5,
    },
    {
        "sku": "DEMO-SPEAKER",
        "name": "Portable Bluetooth Speaker",
        "category": "Electronics",
        "supplier": "tech",
        "cost": "600",
        "price": "999",
        "stock": "0",
        "reorder": "10",
        "safety": "4",
        "lead": 10,
    },
]


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--business-id", required=True)
    parser.add_argument("--user-id", required=True)
    return parser.parse_args()


def validate_target(db, business_id, user_id):
    business = db.execute(
        select(Business).where(Business.id == business_id)
    ).scalar_one_or_none()
    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    membership = db.execute(
        select(BusinessMembership).where(
            BusinessMembership.business_id == business_id,
            BusinessMembership.user_id == user_id,
            BusinessMembership.status == "active",
        )
    ).scalar_one_or_none()
    if not business or not user or not membership:
        raise RuntimeError("User, business, or active membership was not found")
    return business, user


def create_catalog(db, business):
    categories = {}
    for name in ("Electronics", "Accessories", "Beverages"):
        category = Category(
            business_id=business.id,
            name=name,
            description=f"{DEMO_PREFIX}sample {name.lower()} category",
        )
        db.add(category)
        categories[name] = category
    suppliers = {
        "tech": Supplier(
            business_id=business.id,
            name=MARKER_SUPPLIER,
            contact_person="Ana Reyes",
            email="orders@demotech.local",
            phone="+63 917 555 0101",
            payment_terms="Net 30",
            lead_time_days=7,
        ),
        "accessories": Supplier(
            business_id=business.id,
            name="Demo Accessories Wholesale",
            contact_person="Marco Santos",
            email="sales@demoaccessories.local",
            phone="+63 917 555 0102",
            payment_terms="Net 15",
            lead_time_days=5,
        ),
        "local": Supplier(
            business_id=business.id,
            name="Demo Local Goods",
            contact_person="Liza Cruz",
            email="hello@demolocal.local",
            phone="+63 917 555 0103",
            payment_terms="Cash on delivery",
            lead_time_days=3,
        ),
    }
    db.add_all([*categories.values(), *suppliers.values()])
    db.flush()
    products = {}
    historical = datetime.now(timezone.utc) - timedelta(days=150)
    for config in PRODUCTS:
        product = Product(
            business_id=business.id,
            supplier_id=suppliers[config["supplier"]].id,
            category_id=categories[config["category"]].id,
            sku=config["sku"],
            barcode=f"899{len(products) + 1:09d}",
            name=config["name"],
            normalized_name=config["name"].casefold(),
            description="Comprehensive Stockwise demo product",
            brand="Demo Brand",
            unit="unit",
            cost_price=money(config["cost"]),
            selling_price=money(config["price"]),
            reorder_point=Decimal(config["reorder"]),
            safety_stock=Decimal(config["safety"]),
            lead_time_days=config["lead"],
            created_at=historical,
        )
        db.add(product)
        products[config["sku"]] = product
    db.flush()
    for config in PRODUCTS:
        product = products[config["sku"]]
        db.add(
            StockBalance(
                business_id=business.id,
                product_id=product.id,
                quantity=Decimal(config["stock"]),
                reserved_quantity=Decimal("0"),
                average_cost=money(config["cost"]),
            )
        )
    db.flush()
    return products, suppliers


def add_sale_item(db, sale, product, quantity):
    quantity = Decimal(str(quantity))
    line_total = money(product.selling_price * quantity)
    item = SaleItem(
        sale_id=sale.id,
        product_id=product.id,
        quantity=quantity,
        unit_price=product.selling_price,
        unit_cost=product.cost_price,
        discount_amount=Decimal("0"),
        line_total=line_total,
    )
    db.add(item)
    return item, line_total


def create_sales(db, business, user, products):
    now = datetime.now(timezone.utc)
    latest_items = None
    for days_ago in range(74, -1, -1):
        sold_at = now - timedelta(days=days_ago, hours=2)
        sale = Sale(
            business_id=business.id,
            reference_number=f"DEMO-SALE-{75 - days_ago:04d}",
            status="completed",
            sale_date=sold_at,
            subtotal=Decimal("0"),
            total_amount=Decimal("0"),
            payment_method="cash" if days_ago % 2 else "card",
            notes="Generated demo sales history",
            created_by=user.id,
            created_at=sold_at,
        )
        db.add(sale)
        db.flush()
        quantities = {
            "DEMO-EARBUDS": 4 + days_ago % 4,
            "DEMO-USBC": 7 + days_ago % 5,
            "DEMO-CHARGER": 2 + days_ago % 3,
            "DEMO-POWERBANK": 1 + days_ago % 2,
            "DEMO-MOUSE": 1 if days_ago % 3 == 0 else 0,
            "DEMO-PROTECTOR": 1 if days_ago % 4 == 0 else 0,
        }
        total = Decimal("0")
        sale_items = {}
        for sku, quantity in quantities.items():
            if not quantity:
                continue
            item, line_total = add_sale_item(
                db, sale, products[sku], quantity
            )
            sale_items[sku] = item
            total += line_total
            db.add(
                StockMovement(
                    business_id=business.id,
                    product_id=products[sku].id,
                    movement_type="sale",
                    quantity=-Decimal(str(quantity)),
                    unit_cost=products[sku].cost_price,
                    reference_type="sale",
                    reference_id=sale.id,
                    reason="demo_sale",
                    created_by=user.id,
                    created_at=sold_at,
                )
            )
        sale.subtotal = total
        sale.total_amount = total
        latest_items = (sale, sale_items)
    db.flush()
    sale, items = latest_items
    sale.status = "partially_returned"
    returned_at = now - timedelta(hours=1)
    sale_return = SaleReturn(
        business_id=business.id,
        sale_id=sale.id,
        status="completed",
        reason="Customer changed mind",
        notes="Demo partial return",
        refund_amount=products["DEMO-EARBUDS"].selling_price * 2,
        created_by=user.id,
        created_at=returned_at,
    )
    db.add(sale_return)
    db.flush()
    db.add(
        SaleReturnItem(
            return_id=sale_return.id,
            sale_item_id=items["DEMO-EARBUDS"].id,
            product_id=products["DEMO-EARBUDS"].id,
            quantity=Decimal("2"),
            unit_price=products["DEMO-EARBUDS"].selling_price,
            unit_cost=products["DEMO-EARBUDS"].cost_price,
            refund_amount=products["DEMO-EARBUDS"].selling_price * 2,
            created_at=returned_at,
        )
    )
    db.add(
        StockMovement(
            business_id=business.id,
            product_id=products["DEMO-EARBUDS"].id,
            movement_type="return",
            quantity=Decimal("2"),
            unit_cost=products["DEMO-EARBUDS"].cost_price,
            reference_type="sale_return",
            reference_id=sale_return.id,
            reason="customer_return",
            created_by=user.id,
            created_at=returned_at,
        )
    )


def add_purchase_item(db, purchase, product, quantity):
    quantity = Decimal(str(quantity))
    total = money(product.cost_price * quantity)
    db.add(
        PurchaseItem(
            purchase_id=purchase.id,
            product_id=product.id,
            quantity=quantity,
            unit_cost=product.cost_price,
            line_total=total,
        )
    )
    purchase.subtotal += total
    purchase.total_amount += total


def create_purchases(db, business, user, products, suppliers):
    now = datetime.now(timezone.utc)
    definitions = [
        ("RECEIVED", "received", "tech", 60, 55, None),
        ("OVERDUE", "ordered", "tech", 20, None, -5),
        ("INCOMING", "ordered", "accessories", 2, None, 0),
        ("DRAFT", "draft", "local", 0, None, 7),
        ("CANCELLED", "cancelled", "accessories", 12, None, None),
    ]
    purchases = {}
    for (
        label,
        state,
        supplier_key,
        age,
        received_age,
        delivery_offset,
    ) in definitions:
        purchase = Purchase(
            business_id=business.id,
            supplier_id=suppliers[supplier_key].id,
            reference_number=f"DEMO-PO-{label}",
            status=state,
            purchase_date=(now - timedelta(days=age)).date(),
            expected_delivery_date=(
                now + timedelta(days=delivery_offset)
            ).date()
            if delivery_offset is not None
            else None,
            ordered_at=(now - timedelta(days=age))
            if state in ("ordered", "received", "cancelled")
            else None,
            received_at=(now - timedelta(days=received_age))
            if received_age is not None
            else None,
            subtotal=Decimal("0"),
            total_amount=Decimal("0"),
            notes=f"Demo {state} purchase",
            created_by=user.id,
            ordered_by=user.id if state != "draft" else None,
            received_by=user.id if state == "received" else None,
            created_at=now - timedelta(days=max(age, 1)),
        )
        db.add(purchase)
        db.flush()
        purchases[label] = purchase
    add_purchase_item(
        db, purchases["RECEIVED"], products["DEMO-EARBUDS"], 500
    )
    add_purchase_item(
        db, purchases["RECEIVED"], products["DEMO-USBC"], 700
    )
    add_purchase_item(
        db, purchases["OVERDUE"], products["DEMO-CHARGER"], 25
    )
    add_purchase_item(
        db, purchases["INCOMING"], products["DEMO-USBC"], 10
    )
    add_purchase_item(
        db, purchases["DRAFT"], products["DEMO-COFFEE"], 40
    )
    add_purchase_item(
        db, purchases["CANCELLED"], products["DEMO-TABLET"], 30
    )
    for sku, quantity in (("DEMO-EARBUDS", 500), ("DEMO-USBC", 700)):
        product = products[sku]
        db.add(
            StockMovement(
                business_id=business.id,
                product_id=product.id,
                movement_type="purchase",
                quantity=Decimal(quantity),
                unit_cost=product.cost_price,
                reference_type="purchase",
                reference_id=purchases["RECEIVED"].id,
                reason="purchase_received",
                created_by=user.id,
                created_at=purchases["RECEIVED"].received_at,
            )
        )


def create_counts_and_anomalies(db, business, user, products):
    now = datetime.now(timezone.utc)
    finalized = InventoryCount(
        business_id=business.id,
        status="finalized",
        count_date=date.today() - timedelta(days=1),
        notes="Demo finalized count with one significant variance",
        created_by=user.id,
        finalized_by=user.id,
        finalized_at=now - timedelta(hours=12),
        created_at=now - timedelta(days=1),
    )
    draft = InventoryCount(
        business_id=business.id,
        status="draft",
        count_date=date.today(),
        notes="Demo count ready to continue",
        created_by=user.id,
    )
    db.add_all([finalized, draft])
    db.flush()
    for sku, expected, counted in (
        ("DEMO-COFFEE", 126, 114),
        ("DEMO-PROTECTOR", 301, 300),
    ):
        db.add(
            InventoryCountItem(
                inventory_count_id=finalized.id,
                product_id=products[sku].id,
                expected_quantity=Decimal(expected),
                counted_quantity=Decimal(counted),
                notes="Demo physical count",
                counted_at=finalized.finalized_at,
            )
        )
    for sku in ("DEMO-EARBUDS", "DEMO-USBC", "DEMO-COFFEE"):
        balance = db.execute(
            select(StockBalance).where(
                StockBalance.product_id == products[sku].id
            )
        ).scalar_one()
        db.add(
            InventoryCountItem(
                inventory_count_id=draft.id,
                product_id=products[sku].id,
                expected_quantity=balance.quantity,
            )
        )
    db.add_all(
        [
            StockMovement(
                business_id=business.id,
                product_id=products["DEMO-COFFEE"].id,
                movement_type="adjustment",
                quantity=Decimal("-12"),
                unit_cost=products["DEMO-COFFEE"].cost_price,
                reference_type="inventory_count",
                reference_id=finalized.id,
                reason="count_variance",
                notes="Expected 126; physical count was 114",
                created_by=user.id,
                created_at=finalized.finalized_at,
            ),
            StockMovement(
                business_id=business.id,
                product_id=products["DEMO-USBC"].id,
                movement_type="adjustment",
                quantity=Decimal("-15"),
                unit_cost=products["DEMO-USBC"].cost_price,
                reference_type="manual_adjustment",
                reason="correction",
                notes="Demo large adjustment requiring investigation",
                created_by=user.id,
                created_at=now - timedelta(days=2),
            ),
        ]
    )


async def seed(business_id: str, user_id: str):
    with SessionLocal() as db:
        business, user = validate_target(db, business_id, user_id)
        marker = db.execute(
            select(Supplier).where(
                Supplier.business_id == business.id,
                Supplier.name == MARKER_SUPPLIER,
            )
        ).scalar_one_or_none()
        if marker:
            print("Demo data already exists; no records were duplicated.")
            return
        try:
            products, suppliers = create_catalog(db, business)
            create_sales(db, business, user, products)
            create_purchases(db, business, user, products, suppliers)
            create_counts_and_anomalies(db, business, user, products)
            db.commit()
            existing = db.execute(
                select(InventoryBriefing).where(
                    InventoryBriefing.business_id == business.id
                )
            ).scalars().all()
            for briefing in existing:
                db.delete(briefing)
            db.commit()
            settings.NARRATOR_PROVIDER = "template"
            await BriefingService.generate(
                str(business.id), str(user.id), db, force=True
            )
        except Exception:
            db.rollback()
            raise
        print(f"Seeded comprehensive demo data for {business.name}.")


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(seed(arguments.business_id, arguments.user_id))
