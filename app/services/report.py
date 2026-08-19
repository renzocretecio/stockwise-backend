from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from sqlalchemy import func

from app.models.product import Product, Supplier
from app.models.sale import Sale, SaleItem
from app.models.purchase import Purchase, PurchaseItem
from app.models.inventory import StockBalance, StockMovement
from app.schemas.sale import SaleStatus
from app.schemas.purchase import PurchaseStatus


class ReportService:
    # ========================================================================
    # SALES REPORT
    # ========================================================================

    @staticmethod
    def get_sales_report(business_id: str, days: int, db: Session) -> dict:
        """Sales report for the last N days"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        sales = db.execute(
            select(Sale).where(
                Sale.business_id == business_id,
                Sale.created_at >= cutoff,
            )
        ).scalars().all()

        completed_sales = [s for s in sales if s.status == SaleStatus.COMPLETED.value]
        voided_sales = [s for s in sales if s.status == SaleStatus.VOIDED.value]

        total_revenue = sum((s.total_amount for s in completed_sales), Decimal("0"))
        total_profit = sum((s.total_profit for s in completed_sales), Decimal("0"))

        # Items sold count
        sale_ids = [s.id for s in completed_sales]
        total_items_sold = Decimal("0")
        if sale_ids:
            items = db.execute(
                select(SaleItem).where(SaleItem.sale_id.in_(sale_ids))
            ).scalars().all()
            total_items_sold = sum((i.quantity for i in items), Decimal("0"))

        average_sale_value = (
            total_revenue / len(completed_sales) if completed_sales else Decimal("0")
        )

        # Group by day
        by_day_map: dict[str, dict] = {}
        for sale in completed_sales:
            day_key = sale.created_at.date().isoformat()
            if day_key not in by_day_map:
                by_day_map[day_key] = {"revenue": Decimal("0"), "profit": Decimal("0"), "count": 0}
            by_day_map[day_key]["revenue"] += sale.total_amount
            by_day_map[day_key]["profit"] += sale.total_profit
            by_day_map[day_key]["count"] += 1

        by_day = [
            {
                "date": day,
                "revenue": float(data["revenue"]),
                "profit": float(data["profit"]),
                "sales_count": data["count"],
            }
            for day, data in sorted(by_day_map.items())
        ]

        # Top products
        top_products = []
        if sale_ids:
            rows = db.execute(
                select(
                    SaleItem.product_id,
                    func.sum(SaleItem.quantity).label("qty"),
                    func.sum(SaleItem.line_total).label("revenue"),
                )
                .where(SaleItem.sale_id.in_(sale_ids))
                .group_by(SaleItem.product_id)
                .order_by(func.sum(SaleItem.line_total).desc())
                .limit(10)
            ).all()

            for product_id, qty, revenue in rows:
                product = db.execute(
                    select(Product).where(Product.id == product_id)
                ).scalar_one_or_none()

                items_for_product = db.execute(
                    select(SaleItem).where(
                        SaleItem.sale_id.in_(sale_ids),
                        SaleItem.product_id == product_id,
                    )
                ).scalars().all()

                profit = sum(
                    ((i.unit_price - i.unit_cost) * i.quantity for i in items_for_product),
                    Decimal("0"),
                )

                top_products.append({
                    "product_id": str(product_id),
                    "product_name": product.name if product else "Unknown",
                    "quantity_sold": float(qty),
                    "revenue": float(revenue),
                    "profit": float(profit),
                })

        return {
            "period_days": days,
            "summary": {
                "total_sales": len(completed_sales),
                "total_revenue": float(total_revenue),
                "total_profit": float(total_profit),
                "total_items_sold": float(total_items_sold),
                "average_sale_value": float(average_sale_value),
                "voided_count": len(voided_sales),
            },
            "by_day": by_day,
            "top_products": top_products,
        }

    # ========================================================================
    # PURCHASE REPORT
    # ========================================================================

    @staticmethod
    def get_purchase_report(business_id: str, days: int, db: Session) -> dict:
        """Purchase report for the last N days"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        purchases = db.execute(
            select(Purchase).where(
                Purchase.business_id == business_id,
                Purchase.created_at >= cutoff,
            )
        ).scalars().all()

        received = [p for p in purchases if p.status == PurchaseStatus.RECEIVED.value]
        draft = [p for p in purchases if p.status == PurchaseStatus.DRAFT.value]

        total_spent = sum((p.total_amount for p in received), Decimal("0"))
        average_purchase_value = (
            total_spent / len(received) if received else Decimal("0")
        )

        purchase_ids = [p.id for p in received]
        total_items_received = Decimal("0")
        if purchase_ids:
            items = db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id.in_(purchase_ids))
            ).scalars().all()
            total_items_received = sum((i.quantity for i in items), Decimal("0"))

        # Group by day
        by_day_map: dict[str, dict] = {}
        for purchase in received:
            day_key = purchase.created_at.date().isoformat()
            if day_key not in by_day_map:
                by_day_map[day_key] = {"spent": Decimal("0"), "count": 0}
            by_day_map[day_key]["spent"] += purchase.total_amount
            by_day_map[day_key]["count"] += 1

        by_day = [
            {
                "date": day,
                "spent": float(data["spent"]),
                "purchases_count": data["count"],
            }
            for day, data in sorted(by_day_map.items())
        ]

        # Group by supplier
        by_supplier_map: dict[str, dict] = {}
        for purchase in received:
            sid = str(purchase.supplier_id)
            if sid not in by_supplier_map:
                by_supplier_map[sid] = {"spent": Decimal("0"), "count": 0}
            by_supplier_map[sid]["spent"] += purchase.total_amount
            by_supplier_map[sid]["count"] += 1

        by_supplier = []
        for sid, data in sorted(by_supplier_map.items(), key=lambda x: -x[1]["spent"]):
            supplier = db.execute(
                select(Supplier).where(Supplier.id == sid)
            ).scalar_one_or_none()
            by_supplier.append({
                "supplier_id": sid,
                "supplier_name": supplier.name if supplier else "Unknown",
                "total_spent": float(data["spent"]),
                "purchases_count": data["count"],
            })

        return {
            "period_days": days,
            "summary": {
                "total_purchases": len(received),
                "total_spent": float(total_spent),
                "total_items_received": float(total_items_received),
                "average_purchase_value": float(average_purchase_value),
                "pending_count": len(draft),
            },
            "by_day": by_day,
            "by_supplier": by_supplier,
        }

    # ========================================================================
    # INVENTORY REPORT
    # ========================================================================

    @staticmethod
    def get_inventory_report(business_id: str, db: Session) -> dict:
        """Current inventory valuation report"""
        rows = db.execute(
            select(StockBalance, Product)
            .join(Product, Product.id == StockBalance.product_id)
            .where(
                StockBalance.business_id == business_id,
                Product.is_active == True,
            )
        ).all()

        total_stock_value = Decimal("0")
        total_units = Decimal("0")
        low_stock_count = 0
        out_of_stock_count = 0

        by_category_map: dict[str, dict] = {}

        for stock_balance, product in rows:
            stock_value = stock_balance.quantity * stock_balance.average_cost
            total_stock_value += stock_value
            total_units += stock_balance.quantity

            if stock_balance.quantity <= 0:
                out_of_stock_count += 1
            elif stock_balance.quantity <= product.reorder_point:
                low_stock_count += 1

            category = product.category or "Uncategorized"
            if category not in by_category_map:
                by_category_map[category] = {
                    "product_count": 0,
                    "stock_value": Decimal("0"),
                    "total_units": Decimal("0"),
                }
            by_category_map[category]["product_count"] += 1
            by_category_map[category]["stock_value"] += stock_value
            by_category_map[category]["total_units"] += stock_balance.quantity

        by_category = [
            {
                "category": category,
                "product_count": data["product_count"],
                "stock_value": float(data["stock_value"]),
                "total_units": float(data["total_units"]),
            }
            for category, data in sorted(
                by_category_map.items(), key=lambda x: -x[1]["stock_value"]
            )
        ]

        return {
            "summary": {
                "total_products": len(rows),
                "total_stock_value": float(total_stock_value),
                "total_units": float(total_units),
                "low_stock_count": low_stock_count,
                "out_of_stock_count": out_of_stock_count,
            },
            "by_category": by_category,
        }

    # ========================================================================
    # PROFIT REPORT
    # ========================================================================

    @staticmethod
    def get_profit_report(business_id: str, days: int, db: Session) -> dict:
        """Profit report for the last N days, broken down by product"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        sales = db.execute(
            select(Sale).where(
                Sale.business_id == business_id,
                Sale.status == SaleStatus.COMPLETED.value,
                Sale.created_at >= cutoff,
            )
        ).scalars().all()

        sale_ids = [s.id for s in sales]

        total_revenue = Decimal("0")
        total_cost = Decimal("0")
        by_product_map: dict[str, dict] = {}

        if sale_ids:
            items = db.execute(
                select(SaleItem).where(SaleItem.sale_id.in_(sale_ids))
            ).scalars().all()

            for item in items:
                revenue = item.line_total
                cost = item.unit_cost * item.quantity
                total_revenue += revenue
                total_cost += cost

                pid = str(item.product_id)
                if pid not in by_product_map:
                    by_product_map[pid] = {
                        "quantity_sold": Decimal("0"),
                        "revenue": Decimal("0"),
                        "cost": Decimal("0"),
                    }
                by_product_map[pid]["quantity_sold"] += item.quantity
                by_product_map[pid]["revenue"] += revenue
                by_product_map[pid]["cost"] += cost

        total_profit = total_revenue - total_cost
        profit_margin_percent = (
            float((total_profit / total_revenue) * 100) if total_revenue > 0 else 0.0
        )

        by_product = []
        for pid, data in sorted(
            by_product_map.items(),
            key=lambda x: -(x[1]["revenue"] - x[1]["cost"])
        ):
            product = db.execute(
                select(Product).where(Product.id == pid)
            ).scalar_one_or_none()

            profit = data["revenue"] - data["cost"]
            margin = float((profit / data["revenue"]) * 100) if data["revenue"] > 0 else 0.0

            by_product.append({
                "product_id": pid,
                "product_name": product.name if product else "Unknown",
                "quantity_sold": float(data["quantity_sold"]),
                "revenue": float(data["revenue"]),
                "cost": float(data["cost"]),
                "profit": float(profit),
                "margin_percent": round(margin, 2),
            })

        return {
            "period_days": days,
            "summary": {
                "total_revenue": float(total_revenue),
                "total_cost": float(total_cost),
                "total_profit": float(total_profit),
                "profit_margin_percent": round(profit_margin_percent, 2),
            },
            "by_product": by_product,
        }

    # ========================================================================
    # LOW STOCK REPORT
    # ========================================================================

    @staticmethod
    def get_low_stock_report(business_id: str, db: Session) -> dict:
        """Products at or below reorder point"""
        rows = db.execute(
            select(StockBalance, Product)
            .join(Product, Product.id == StockBalance.product_id)
            .where(
                StockBalance.business_id == business_id,
                Product.is_active == True,
                StockBalance.quantity <= Product.reorder_point,
            )
            .order_by(StockBalance.quantity.asc())
        ).all()

        items = []
        for stock_balance, product in rows:
            supplier = None
            if product.supplier_id:
                supplier = db.execute(
                    select(Supplier).where(Supplier.id == product.supplier_id)
                ).scalar_one_or_none()

            item_status = "out_of_stock" if stock_balance.quantity <= 0 else "low_stock"

            items.append({
                "product_id": str(product.id),
                "product_name": product.name,
                "sku": product.sku,
                "quantity": float(stock_balance.quantity),
                "reorder_point": float(product.reorder_point),
                "safety_stock": float(product.safety_stock),
                "supplier_id": str(product.supplier_id) if product.supplier_id else None,
                "supplier_name": supplier.name if supplier else None,
                "lead_time_days": product.lead_time_days,
                "status": item_status,
            })

        return {
            "total_items": len(items),
            "items": items,
        }

    # ========================================================================
    # STOCK MOVEMENT REPORT
    # ========================================================================

    @staticmethod
    def get_stock_movement_report(business_id: str, days: int, db: Session) -> dict:
        """Summary of stock movements by type"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        rows = db.execute(
            select(
                StockMovement.movement_type,
                func.count().label("total"),
                func.sum(StockMovement.quantity_change).label("total_change"),
            )
            .where(
                StockMovement.business_id == business_id,
                StockMovement.created_at >= cutoff,
            )
            .group_by(StockMovement.movement_type)
        ).all()

        by_type = [
            {
                "movement_type": movement_type,
                "total_movements": total,
                "total_quantity_change": float(total_change or 0),
            }
            for movement_type, total, total_change in rows
        ]

        total_movements = sum(item["total_movements"] for item in by_type)

        return {
            "period_days": days,
            "by_type": by_type,
            "total_movements": total_movements,
        }