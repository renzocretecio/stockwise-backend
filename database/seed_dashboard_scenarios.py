"""Seed current dashboard risk, forecast, and anomaly scenarios.

This script updates a known demo grocery catalog without adding products.
It is safe to rerun: sales, the physical count, and the adjustment anomaly
are updated through stable marker values.

Usage:
    PYTHONPATH=. venv/bin/python database/seed_dashboard_scenarios.py \
        --business-id <uuid> --user-id <uuid>
"""

import argparse
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config.database import SessionLocal
from app.models.auth import User
from app.models.business import Business
from app.models.inventory import (
    InventoryCount,
    InventoryCountItem,
    StockBalance,
    StockMovement,
)
from app.models.membership import BusinessMembership
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.services.dashboard import DashboardService


SALE_PREFIX = "DASHBOARD-DEMO-SALE-"
COUNT_MARKER = "Dashboard demo count variance"
ADJUSTMENT_MARKER = "dashboard_demo_large_adjustment"

SCENARIOS = {
    "MG-WATER": {"stock": "0", "daily_sales": "12"},
    "MG-NOODLES": {"stock": "18", "daily_sales": "8"},
    "MG-SARDINES": {"stock": "24", "daily_sales": "6"},
    "MG-COFFEE": {"stock": "17", "daily_sales": "4"},
    "MG-RICE-5KG": {"stock": "20", "daily_sales": "5"},
}


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
        raise RuntimeError(
            "User, business, or active membership was not found."
        )
    return business, user


def load_products(db, business_id):
    products = db.execute(
        select(Product).where(
            Product.business_id == business_id,
            Product.sku.in_(SCENARIOS),
        )
    ).scalars().all()
    by_sku = {product.sku: product for product in products}
    missing = sorted(set(SCENARIOS) - set(by_sku))

    if missing:
        raise RuntimeError(
            "Required demo products are missing: " + ", ".join(missing)
        )
    return by_sku


def update_balances(db, business_id, products):
    for sku, scenario in SCENARIOS.items():
        product = products[sku]
        balance = db.execute(
            select(StockBalance).where(
                StockBalance.business_id == business_id,
                StockBalance.product_id == product.id,
            )
        ).scalar_one()
        balance.quantity = Decimal(scenario["stock"])
        balance.reserved_quantity = Decimal("0")
        db.add(balance)


def upsert_sales(db, business, user, products):
    now = datetime.now(timezone.utc)

    for days_ago in range(29, -1, -1):
        sequence = 30 - days_ago
        reference = f"{SALE_PREFIX}{sequence:02d}"
        sold_at = now - timedelta(days=days_ago)
        sale = db.execute(
            select(Sale).where(
                Sale.business_id == business.id,
                Sale.reference_number == reference,
            )
        ).scalar_one_or_none()

        if sale is None:
            sale = Sale(
                business_id=business.id,
                reference_number=reference,
                created_by=user.id,
            )
            db.add(sale)
            db.flush()

        sale.status = "completed"
        sale.sale_date = sold_at
        sale.payment_method = "cash"
        sale.notes = "Dashboard forecast demo history"
        sale.created_at = sold_at

        existing_items = {
            item.product_id: item
            for item in db.execute(
                select(SaleItem).where(SaleItem.sale_id == sale.id)
            ).scalars()
        }
        total = Decimal("0")
        for sku, scenario in SCENARIOS.items():
            product = products[sku]
            quantity = Decimal(scenario["daily_sales"])
            line_total = quantity * Decimal(product.selling_price)
            item = existing_items.get(product.id)

            if item is None:
                item = SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=product.selling_price,
                    unit_cost=product.cost_price,
                    discount_amount=Decimal("0"),
                    line_total=line_total,
                )
            else:
                item.quantity = quantity
                item.unit_price = product.selling_price
                item.unit_cost = product.cost_price
                item.discount_amount = Decimal("0")
                item.line_total = line_total
            db.add(item)
            total += line_total

        sale.subtotal = total
        sale.discount_amount = Decimal("0")
        sale.tax_amount = Decimal("0")
        sale.total_amount = total
        db.add(sale)


def upsert_count_anomaly(db, business, user, products):
    now = datetime.now(timezone.utc)
    count = db.execute(
        select(InventoryCount).where(
            InventoryCount.business_id == business.id,
            InventoryCount.notes == COUNT_MARKER,
        )
    ).scalar_one_or_none()

    if count is None:
        count = InventoryCount(
            business_id=business.id,
            notes=COUNT_MARKER,
            created_by=user.id,
        )
        db.add(count)
        db.flush()

    count.status = "finalized"
    count.count_date = date.today()
    count.finalized_by = user.id
    count.finalized_at = now - timedelta(hours=1)
    count.created_at = now - timedelta(hours=2)
    db.add(count)

    product = products["MG-SARDINES"]
    balance = db.execute(
        select(StockBalance).where(
            StockBalance.product_id == product.id
        )
    ).scalar_one()
    item = db.execute(
        select(InventoryCountItem).where(
            InventoryCountItem.inventory_count_id == count.id,
            InventoryCountItem.product_id == product.id,
        )
    ).scalar_one_or_none()

    if item is None:
        item = InventoryCountItem(
            inventory_count_id=count.id,
            product_id=product.id,
        )
    item.expected_quantity = Decimal(balance.quantity) + Decimal("14")
    item.counted_quantity = Decimal(balance.quantity)
    item.notes = "Demo variance requiring investigation"
    item.counted_at = count.finalized_at
    db.add(item)


def upsert_adjustment_anomaly(db, business, user, products):
    movement = db.execute(
        select(StockMovement).where(
            StockMovement.business_id == business.id,
            StockMovement.reason == ADJUSTMENT_MARKER,
        )
    ).scalar_one_or_none()
    product = products["MG-COFFEE"]

    if movement is None:
        movement = StockMovement(
            business_id=business.id,
            product_id=product.id,
            movement_type="adjustment",
            quantity=Decimal("-15"),
            unit_cost=product.cost_price,
            reference_type="manual_adjustment",
            reason=ADJUSTMENT_MARKER,
            created_by=user.id,
        )

    movement.product_id = product.id
    movement.quantity = Decimal("-15")
    movement.unit_cost = product.cost_price
    movement.notes = "Demo large adjustment requiring review"
    movement.created_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    db.add(movement)


def summarize_dashboard(business_id, db):
    dashboard = DashboardService.get_dashboard(str(business_id), db)
    risk = dashboard["inventory_risk"]
    return {
        "out_of_stock": risk["out_of_stock_skus"],
        "low_stock": risk["low_stock_skus"],
        "below_reorder": risk["below_reorder_point"],
        "under_7_days": risk["below_days_of_stock"],
        "forecasts": len(dashboard["forecasts"]),
        "anomalies": len(dashboard["anomalies"]),
    }


async def seed(business_id: str, user_id: str):
    with SessionLocal() as db:
        business, user = validate_target(db, business_id, user_id)
        products = load_products(db, business.id)

        try:
            update_balances(db, business.id, products)
            upsert_sales(db, business, user, products)
            upsert_count_anomaly(db, business, user, products)
            upsert_adjustment_anomaly(db, business, user, products)
            db.commit()
        except Exception:
            db.rollback()
            raise

        summary = summarize_dashboard(business.id, db)
        print(f"Seeded dashboard scenarios for {business.name}: {summary}")


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(seed(arguments.business_id, arguments.user_id))
