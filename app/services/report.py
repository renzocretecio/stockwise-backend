from decimal import Decimal
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlmodel import Session, select
from sqlalchemy import func

from app.models.product import Product, Supplier
from app.models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem
from app.models.purchase import Purchase, PurchaseItem
from app.models.inventory import (
    InventoryCount,
    InventoryCountItem,
    StockBalance,
    StockMovement,
)
from app.schemas.sale import SaleStatus
from app.schemas.purchase import PurchaseStatus


class ReportService:
    # ========================================================================
    # OPERATIONAL METRICS
    # ========================================================================

    @staticmethod
    def get_operational_metrics(
        *,
        business_id: str,
        db: Session,
        start_date: date,
        end_date: date,
        timezone_name: str,
    ) -> dict:
        """Calculate auditable operational metrics for a calendar range."""
        try:
            zone = ZoneInfo(timezone_name)
        except Exception:
            zone = ZoneInfo("UTC")
        range_start = datetime.combine(
            start_date,
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        range_end = datetime.combine(
            end_date + timedelta(days=1),
            time.min,
            tzinfo=zone,
        ).astimezone(timezone.utc)
        period_days = (end_date - start_date).days + 1

        count_rows = db.execute(
            select(
                InventoryCountItem.expected_quantity,
                InventoryCountItem.counted_quantity,
            )
            .join(
                InventoryCount,
                InventoryCount.id
                == InventoryCountItem.inventory_count_id,
            )
            .where(
                InventoryCount.business_id == business_id,
                InventoryCount.status == "finalized",
                InventoryCount.finalized_at >= range_start,
                InventoryCount.finalized_at < range_end,
                InventoryCountItem.counted_quantity.is_not(None),
            )
        ).all()
        counted_items = len(count_rows)
        accurate_items = sum(
            1
            for expected, counted in count_rows
            if Decimal(expected) == Decimal(counted)
        )

        balances = db.execute(
            select(StockBalance).where(
                StockBalance.business_id == business_id
            )
        ).scalars().all()
        inventory_value = sum(
            (
                max(Decimal("0"), Decimal(balance.quantity))
                * Decimal(balance.average_cost)
                for balance in balances
            ),
            Decimal("0"),
        )
        average_cost_by_product = {
            balance.product_id: Decimal(balance.average_cost)
            for balance in balances
        }

        sale_cogs = db.execute(
            select(
                SaleItem.product_id,
                SaleItem.quantity,
                SaleItem.unit_cost,
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.business_id == business_id,
                Sale.status.in_({
                    SaleStatus.COMPLETED.value,
                    SaleStatus.PARTIALLY_RETURNED.value,
                    SaleStatus.RETURNED.value,
                }),
                Sale.sale_date >= range_start,
                Sale.sale_date < range_end,
            )
        ).all()
        return_cogs = db.execute(
            select(
                SaleReturnItem.product_id,
                SaleReturnItem.quantity,
                SaleReturnItem.unit_cost,
            )
            .join(
                SaleReturn,
                SaleReturn.id == SaleReturnItem.return_id,
            )
            .where(
                SaleReturn.business_id == business_id,
                SaleReturn.status == "completed",
                SaleReturn.created_at >= range_start,
                SaleReturn.created_at < range_end,
            )
        ).all()
        sold_cost = sum(
            (
                Decimal(quantity) * Decimal(unit_cost)
                for _, quantity, unit_cost in sale_cogs
            ),
            Decimal("0"),
        )
        returned_cost = sum(
            (
                Decimal(quantity) * Decimal(unit_cost)
                for _, quantity, unit_cost in return_cogs
            ),
            Decimal("0"),
        )
        period_cogs = max(Decimal("0"), sold_cost - returned_cost)

        movement_rows = db.execute(
            select(StockMovement).where(
                StockMovement.business_id == business_id,
                StockMovement.quantity < 0,
                StockMovement.created_at >= range_start,
                StockMovement.created_at < range_end,
            )
        ).scalars().all()
        shrinkage_reasons = {
            "damage",
            "expiry",
            "physical_count",
            "shrinkage",
        }
        shrinkage_movements = [
            movement
            for movement in movement_rows
            if movement.movement_type in {"damage", "expired"}
            or (
                movement.movement_type == "adjustment"
                and movement.reason in shrinkage_reasons
            )
        ]
        shrinkage_units = sum(
            (abs(Decimal(item.quantity)) for item in shrinkage_movements),
            Decimal("0"),
        )
        shrinkage_value = sum(
            (
                abs(Decimal(item.quantity))
                * (
                    Decimal(item.unit_cost)
                    if item.unit_cost is not None
                    else average_cost_by_product.get(
                        item.product_id,
                        Decimal("0"),
                    )
                )
                for item in shrinkage_movements
            ),
            Decimal("0"),
        )

        purchases = db.execute(
            select(Purchase).where(
                Purchase.business_id == business_id,
                Purchase.ordered_at >= range_start,
                Purchase.ordered_at < range_end,
                Purchase.status.in_({
                    PurchaseStatus.ORDERED.value,
                    PurchaseStatus.RECEIVED.value,
                }),
            )
        ).scalars().all()
        ordered_purchases = len(purchases)
        received_purchases = sum(
            1
            for purchase in purchases
            if purchase.status == PurchaseStatus.RECEIVED.value
            and purchase.received_at is not None
            and purchase.received_at < range_end
        )

        return ReportService._build_operational_metrics(
            period_days=period_days,
            counted_items=counted_items,
            accurate_items=accurate_items,
            inventory_value=inventory_value,
            period_cogs=period_cogs,
            shrinkage_units=shrinkage_units,
            shrinkage_value=shrinkage_value,
            ordered_purchases=ordered_purchases,
            received_purchases=received_purchases,
        )

    @staticmethod
    def _build_operational_metrics(
        *,
        period_days: int,
        counted_items: int,
        accurate_items: int,
        inventory_value: Decimal,
        period_cogs: Decimal,
        shrinkage_units: Decimal,
        shrinkage_value: Decimal,
        ordered_purchases: int,
        received_purchases: int,
    ) -> dict:
        stock_accuracy = (
            Decimal(accurate_items) / Decimal(counted_items) * 100
            if counted_items
            else None
        )
        daily_cogs = period_cogs / Decimal(period_days)
        inventory_days = (
            inventory_value / daily_cogs
            if daily_cogs > 0
            else None
        )
        shrinkage_rate = (
            shrinkage_value / inventory_value * 100
            if inventory_value > 0
            else None
        )
        receipt_rate = (
            Decimal(received_purchases)
            / Decimal(ordered_purchases)
            * 100
            if ordered_purchases
            else None
        )

        return {
            "period_days": period_days,
            "stock_accuracy_rate": (
                float(round(stock_accuracy, 1))
                if stock_accuracy is not None
                else None
            ),
            "counted_items": counted_items,
            "accurate_items": accurate_items,
            "inventory_days": (
                float(round(inventory_days, 1))
                if inventory_days is not None
                else None
            ),
            "inventory_value": float(inventory_value),
            "period_cogs": float(period_cogs),
            "shrinkage_rate": (
                float(round(shrinkage_rate, 2))
                if shrinkage_rate is not None
                else None
            ),
            "shrinkage_units": float(shrinkage_units),
            "shrinkage_value": float(shrinkage_value),
            "receipt_completion_rate": (
                float(round(receipt_rate, 1))
                if receipt_rate is not None
                else None
            ),
            "ordered_purchases": ordered_purchases,
            "received_purchases": received_purchases,
        }

    # ========================================================================
    # SALES REPORT
    # ========================================================================

    @staticmethod
    def get_sales_report(
        business_id: str,
        days: int,
        db: Session,
        start_date: date | None = None,
        end_date: date | None = None,
        timezone_name: str = "UTC",
    ) -> dict:
        """Return-aware sales report for a period or explicit date range."""
        range_end = None
        period_days = days

        if start_date is not None and end_date is not None:
            try:
                zone = ZoneInfo(timezone_name)
            except Exception:
                zone = ZoneInfo("UTC")
            cutoff = datetime.combine(
                start_date,
                time.min,
                tzinfo=zone,
            ).astimezone(timezone.utc)
            range_end = datetime.combine(
                end_date + timedelta(days=1),
                time.min,
                tzinfo=zone,
            ).astimezone(timezone.utc)
            period_days = (end_date - start_date).days + 1
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        sale_filters = [
            Sale.business_id == business_id,
            Sale.sale_date >= cutoff,
        ]
        return_filters = [
            SaleReturn.business_id == business_id,
            SaleReturn.status == "completed",
            SaleReturn.created_at >= cutoff,
        ]
        if range_end is not None:
            sale_filters.append(Sale.sale_date < range_end)
            return_filters.append(SaleReturn.created_at < range_end)

        sales = db.execute(
            select(Sale).where(*sale_filters)
        ).scalars().all()

        reportable_statuses = {
            SaleStatus.COMPLETED.value,
            SaleStatus.PARTIALLY_RETURNED.value,
            SaleStatus.RETURNED.value,
        }
        completed_sales = [s for s in sales if s.status in reportable_statuses]
        voided_sales = [s for s in sales if s.status == SaleStatus.VOIDED.value]
        sale_ids = [s.id for s in completed_sales]
        sale_items = []
        if sale_ids:
            sale_items = db.execute(
                select(SaleItem).where(SaleItem.sale_id.in_(sale_ids))
            ).scalars().all()

        completed_returns = db.execute(
            select(SaleReturn).where(*return_filters)
        ).scalars().all()
        return_ids = [sale_return.id for sale_return in completed_returns]
        return_items = []
        if return_ids:
            return_items = db.execute(
                select(SaleReturnItem).where(
                    SaleReturnItem.return_id.in_(return_ids)
                )
            ).scalars().all()

        product_ids = {
            item.product_id for item in [*sale_items, *return_items]
        }
        products = []
        if product_ids:
            products = db.execute(
                select(Product).where(Product.id.in_(product_ids))
            ).scalars().all()
        product_names = {
            product.id: product.name for product in products
        }

        report = ReportService._build_sales_report(
            days=period_days,
            completed_sales=completed_sales,
            voided_sales=voided_sales,
            sale_items=sale_items,
            completed_returns=completed_returns,
            return_items=return_items,
            product_names=product_names,
            timezone_name=timezone_name,
        )

        products_by_id = {
            str(product.id): product for product in products
        }
        stock_by_product: dict[str, StockBalance] = {}
        if product_ids:
            balances = db.execute(
                select(StockBalance).where(
                    StockBalance.product_id.in_(product_ids)
                )
            ).scalars().all()
            stock_by_product = {
                str(balance.product_id): balance for balance in balances
            }

        ReportService._add_product_velocity(
            products=report["top_products"],
            products_by_id=products_by_id,
            stock_by_product=stock_by_product,
            period_days=period_days,
        )
        report["slow_products"] = ReportService._get_slow_products(
            business_id=business_id,
            db=db,
            timezone_name=timezone_name,
            reportable_statuses=reportable_statuses,
        )
        return report

    @staticmethod
    def _add_product_velocity(
        *,
        products: list[dict],
        products_by_id: dict[str, Product],
        stock_by_product: dict[str, StockBalance],
        period_days: int,
    ) -> None:
        """Add deterministic sales velocity and stock coverage fields."""
        for item in products:
            product_id = item["product_id"]
            product = products_by_id.get(product_id)
            balance = stock_by_product.get(product_id)
            current_stock = Decimal("0")
            if balance is not None:
                current_stock = max(
                    Decimal("0"),
                    Decimal(balance.quantity)
                    - Decimal(balance.reserved_quantity),
                )

            quantity_sold = Decimal(str(item["quantity_sold"]))
            units_per_day = quantity_sold / Decimal(period_days)
            days_remaining = (
                current_stock / units_per_day
                if units_per_day > 0
                else None
            )

            item.update({
                "sku": product.sku if product is not None else None,
                "units_per_day": float(round(units_per_day, 3)),
                "current_stock": float(current_stock),
                "days_of_stock_remaining": (
                    float(round(days_remaining, 1))
                    if days_remaining is not None
                    else None
                ),
            })

    @staticmethod
    def _get_slow_products(
        *,
        business_id: str,
        db: Session,
        timezone_name: str,
        reportable_statuses: set[str],
    ) -> list[dict]:
        """Return stocked products with no completed sale for 30+ days."""
        rows = db.execute(
            select(Product, StockBalance)
            .join(
                StockBalance,
                StockBalance.product_id == Product.id,
            )
            .where(
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).all()

        last_sale_rows = db.execute(
            select(
                SaleItem.product_id,
                func.max(Sale.sale_date),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.business_id == business_id,
                Sale.status.in_(reportable_statuses),
            )
            .group_by(SaleItem.product_id)
        ).all()
        last_sale_by_product = dict(last_sale_rows)

        try:
            zone = ZoneInfo(timezone_name)
        except Exception:
            zone = ZoneInfo("UTC")
        today = datetime.now(zone).date()

        slow_products = []
        for product, balance in rows:
            current_stock = Decimal(balance.quantity)
            current_stock -= Decimal(balance.reserved_quantity)
            if current_stock <= 0:
                continue

            last_sale_at = last_sale_by_product.get(product.id)
            activity_at = last_sale_at or product.created_at
            if activity_at.tzinfo is None:
                activity_at = activity_at.replace(tzinfo=timezone.utc)
            activity_date = activity_at.astimezone(zone).date()
            days_without_sale = max((today - activity_date).days, 0)
            if days_without_sale < 30:
                continue

            if days_without_sale >= 90:
                classification = "dead_stock"
            elif days_without_sale >= 60:
                classification = "very_slow"
            else:
                classification = "slow"

            inventory_value = (
                Decimal(balance.quantity)
                * Decimal(balance.average_cost)
            )
            slow_products.append({
                "product_id": str(product.id),
                "product_name": product.name,
                "sku": product.sku,
                "current_stock": float(current_stock),
                "inventory_value": float(inventory_value),
                "last_sale_date": (
                    activity_date.isoformat()
                    if last_sale_at is not None
                    else None
                ),
                "days_without_sale": days_without_sale,
                "classification": classification,
            })

        slow_products.sort(
            key=lambda item: (
                item["days_without_sale"],
                item["inventory_value"],
            ),
            reverse=True,
        )
        return slow_products[:10]

    @staticmethod
    def _build_sales_report(
        *,
        days: int,
        completed_sales: list,
        voided_sales: list,
        sale_items: list,
        completed_returns: list,
        return_items: list,
        product_names: dict,
        timezone_name: str = "UTC",
    ) -> dict:
        """Build net sales metrics from loaded sales and return records."""
        zero = Decimal("0")
        total_revenue = sum(
            (Decimal(sale.total_amount) for sale in completed_sales),
            zero,
        )
        total_revenue -= sum(
            (
                Decimal(sale_return.refund_amount)
                for sale_return in completed_returns
            ),
            zero,
        )
        total_items_sold = sum(
            (Decimal(item.quantity) for item in sale_items),
            zero,
        )
        total_items_sold -= sum(
            (Decimal(item.quantity) for item in return_items),
            zero,
        )

        profit_by_sale: dict[object, Decimal] = {}
        product_metrics: dict[object, dict[str, Decimal]] = {}
        for item in sale_items:
            profit = (
                Decimal(item.unit_price) - Decimal(item.unit_cost)
            ) * Decimal(item.quantity)
            profit_by_sale[item.sale_id] = (
                profit_by_sale.get(item.sale_id, zero) + profit
            )
            metrics = product_metrics.setdefault(
                item.product_id,
                {"quantity": zero, "revenue": zero, "profit": zero},
            )
            metrics["quantity"] += Decimal(item.quantity)
            metrics["revenue"] += Decimal(item.line_total)
            metrics["profit"] += profit

        return_profit_by_return: dict[object, Decimal] = {}
        for item in return_items:
            refund = Decimal(item.refund_amount)
            restored_cost = Decimal(item.unit_cost) * Decimal(item.quantity)
            profit_reversal = refund - restored_cost
            return_profit_by_return[item.return_id] = (
                return_profit_by_return.get(item.return_id, zero)
                + profit_reversal
            )
            metrics = product_metrics.setdefault(
                item.product_id,
                {"quantity": zero, "revenue": zero, "profit": zero},
            )
            metrics["quantity"] -= Decimal(item.quantity)
            metrics["revenue"] -= refund
            metrics["profit"] -= profit_reversal

        total_profit = sum(profit_by_sale.values(), zero)
        total_profit -= sum(return_profit_by_return.values(), zero)
        average_sale_value = (
            total_revenue / len(completed_sales)
            if completed_sales
            else zero
        )

        by_day_map: dict[str, dict] = {}

        try:
            report_zone = ZoneInfo(timezone_name)
        except Exception:
            report_zone = ZoneInfo("UTC")

        def day_metrics(value: datetime) -> dict:
            day_key = value.astimezone(report_zone).date().isoformat()
            return by_day_map.setdefault(
                day_key,
                {"revenue": zero, "profit": zero, "count": 0},
            )

        for sale in completed_sales:
            metrics = day_metrics(sale.sale_date)
            metrics["revenue"] += Decimal(sale.total_amount)
            metrics["profit"] += profit_by_sale.get(sale.id, zero)
            metrics["count"] += 1
        for sale_return in completed_returns:
            metrics = day_metrics(sale_return.created_at)
            metrics["revenue"] -= Decimal(sale_return.refund_amount)
            metrics["profit"] -= return_profit_by_return.get(
                sale_return.id,
                zero,
            )

        by_day = [
            {
                "date": day,
                "revenue": float(data["revenue"]),
                "profit": float(data["profit"]),
                "sales_count": data["count"],
            }
            for day, data in sorted(by_day_map.items())
        ]

        top_products = [
            {
                "product_id": str(product_id),
                "product_name": product_names.get(
                    product_id,
                    "Unknown",
                ),
                "quantity_sold": float(metrics["quantity"]),
                "revenue": float(metrics["revenue"]),
                "profit": float(metrics["profit"]),
            }
            for product_id, metrics in sorted(
                product_metrics.items(),
                key=lambda entry: entry[1]["revenue"],
                reverse=True,
            )
            if metrics["quantity"] > 0 or metrics["revenue"] > 0
        ][:10]

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
        pending = [
            p for p in purchases
            if p.status in {PurchaseStatus.DRAFT.value, PurchaseStatus.ORDERED.value}
        ]

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
            day_key = (purchase.received_at or purchase.created_at).date().isoformat()
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
                "pending_count": len(pending),
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

            category = product.category.name if product.category else "Uncategorized"
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
                Sale.status.in_([
                    SaleStatus.COMPLETED.value,
                    SaleStatus.PARTIALLY_RETURNED.value,
                    SaleStatus.RETURNED.value,
                ]),
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
                func.sum(StockMovement.quantity).label("total_change"),
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
