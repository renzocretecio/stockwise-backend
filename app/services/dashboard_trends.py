from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.models.inventory import StockBalance, StockMovement
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem


SALE_STATUSES = ("completed", "partially_returned", "returned")
Granularity = Literal["day", "week", "month"]


def trend_granularity(period_days: int) -> Granularity:
    if period_days <= 60:
        return "day"
    if period_days <= 180:
        return "week"
    return "month"


def trend_bucket_start(value: date, granularity: Granularity) -> date:
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1)
    return value


class DashboardTrendsService:
    @staticmethod
    def _zone(timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            return ZoneInfo("UTC")

    @staticmethod
    def _bounds(value: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
        start = datetime.combine(value, time.min, tzinfo=zone)
        start = start.astimezone(timezone.utc)
        return start, start + timedelta(days=1)

    @staticmethod
    def get_trends(
        *,
        business_id: str,
        db: Session,
        start_date: date,
        end_date: date,
        timezone_name: str,
    ) -> dict:
        zone = DashboardTrendsService._zone(timezone_name)
        today = datetime.now(zone).date()
        effective_end = min(end_date, today)
        start_at, _ = DashboardTrendsService._bounds(start_date, zone)
        _, end_at = DashboardTrendsService._bounds(effective_end, zone)

        daily = {
            start_date + timedelta(days=index): {
                "revenue": Decimal("0"),
                "gross_profit": Decimal("0"),
                "items_sold": Decimal("0"),
                "order_count": 0,
                "cogs": Decimal("0"),
                "purchase_receipts": Decimal("0"),
                "adjustments": Decimal("0"),
                "discrepancies": Decimal("0"),
            }
            for index in range((effective_end - start_date).days + 1)
        }

        sales = db.execute(
            select(Sale).where(
                Sale.business_id == business_id,
                Sale.status.in_(SALE_STATUSES),
                Sale.sale_date >= start_at,
                Sale.sale_date < end_at,
            )
        ).scalars().all()
        sale_ids = [sale.id for sale in sales]
        sale_items = db.execute(
            select(SaleItem).where(SaleItem.sale_id.in_(sale_ids))
        ).scalars().all() if sale_ids else []
        items_by_sale = defaultdict(list)
        for item in sale_items:
            items_by_sale[item.sale_id].append(item)

        for sale in sales:
            day = sale.sale_date.astimezone(zone).date()
            metrics = daily[day]
            metrics["revenue"] += Decimal(sale.total_amount)
            metrics["order_count"] += 1
            for item in items_by_sale[sale.id]:
                quantity = Decimal(item.quantity)
                cost = quantity * Decimal(item.unit_cost)
                metrics["items_sold"] += quantity
                metrics["cogs"] += cost
                metrics["gross_profit"] += (
                    Decimal(item.unit_price) - Decimal(item.unit_cost)
                ) * quantity

        returns = db.execute(
            select(SaleReturn).where(
                SaleReturn.business_id == business_id,
                SaleReturn.status == "completed",
                SaleReturn.created_at >= start_at,
                SaleReturn.created_at < end_at,
            )
        ).scalars().all()
        return_ids = [sale_return.id for sale_return in returns]
        return_items = db.execute(
            select(SaleReturnItem).where(
                SaleReturnItem.return_id.in_(return_ids)
            )
        ).scalars().all() if return_ids else []
        items_by_return = defaultdict(list)
        for item in return_items:
            items_by_return[item.return_id].append(item)

        for sale_return in returns:
            day = sale_return.created_at.astimezone(zone).date()
            metrics = daily[day]
            metrics["revenue"] -= Decimal(sale_return.refund_amount)
            for item in items_by_return[sale_return.id]:
                quantity = Decimal(item.quantity)
                restored_cost = quantity * Decimal(item.unit_cost)
                metrics["items_sold"] -= quantity
                metrics["cogs"] -= restored_cost
                metrics["gross_profit"] -= (
                    Decimal(item.refund_amount) - restored_cost
                )

        movement_end = datetime.now(timezone.utc)
        movements = db.execute(
            select(StockMovement).where(
                StockMovement.business_id == business_id,
                StockMovement.created_at >= start_at,
                StockMovement.created_at <= movement_end,
            )
        ).scalars().all()
        movements_by_day = defaultdict(list)
        for movement in movements:
            day = movement.created_at.astimezone(zone).date()
            movements_by_day[day].append(movement)
            if day not in daily:
                continue
            quantity = Decimal(movement.quantity)
            if movement.movement_type == "purchase":
                daily[day]["purchase_receipts"] += max(
                    Decimal("0"), quantity
                )
            elif movement.movement_type == "adjustment":
                is_discrepancy = (
                    movement.reference_type == "inventory_count"
                    or movement.reason == "physical_count"
                )
                key = "discrepancies" if is_discrepancy else "adjustments"
                daily[day][key] += quantity

        rows = db.execute(
            select(Product, StockBalance)
            .join(StockBalance, StockBalance.product_id == Product.id)
            .where(
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).all()
        quantities = {
            product.id: Decimal(balance.quantity)
            for product, balance in rows
        }
        costs = {
            product.id: Decimal(balance.average_cost)
            for product, balance in rows
        }

        history_start = start_at - timedelta(days=90)
        sale_history = db.execute(
            select(SaleItem.product_id, Sale.sale_date)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.business_id == business_id,
                Sale.status.in_(SALE_STATUSES),
                Sale.sale_date >= history_start,
                Sale.sale_date < end_at,
            )
        ).all()
        sale_dates = defaultdict(list)
        for product_id, sold_at in sale_history:
            sale_dates[product_id].append(sold_at.astimezone(zone).date())
        for values in sale_dates.values():
            values.sort()

        inventory_by_day = {}
        cursor = today
        while cursor >= start_date:
            if cursor <= effective_end:
                inventory_by_day[cursor] = (
                    DashboardTrendsService._inventory_metrics(
                        cursor,
                        rows,
                        quantities,
                        costs,
                        sale_dates,
                        zone,
                    )
                )
            for movement in movements_by_day.get(cursor, []):
                quantities[movement.product_id] -= Decimal(
                    movement.quantity
                )
            cursor -= timedelta(days=1)

        granularity = trend_granularity(len(daily))
        points = DashboardTrendsService._aggregate(
            daily,
            inventory_by_day,
            granularity,
        )
        return {
            "start_date": start_date,
            "end_date": effective_end,
            "granularity": granularity,
            "inventory_valuation_method": (
                "Historical quantities valued at current average cost"
            ),
            "points": points,
        }

    @staticmethod
    def _inventory_metrics(
        target: date,
        rows: list,
        quantities: dict,
        costs: dict,
        sale_dates: dict,
        zone: ZoneInfo,
    ) -> dict:
        inventory_value = Decimal("0")
        dead_stock_value = Decimal("0")
        stockouts = 0
        for product, _ in rows:
            created_at = product.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            created_date = created_at.astimezone(zone).date()
            if created_date > target:
                continue
            quantity = quantities.get(product.id, Decimal("0"))
            if quantity <= 0:
                stockouts += 1
                continue
            value = quantity * costs.get(product.id, Decimal("0"))
            inventory_value += value
            product_sales = sale_dates.get(product.id, [])
            position = bisect_right(product_sales, target)
            last_sale = product_sales[position - 1] if position else None
            activity_date = last_sale or created_date
            if (target - activity_date).days >= 90:
                dead_stock_value += value
        return {
            "inventory_value": inventory_value,
            "dead_stock_value": dead_stock_value,
            "stockout_count": stockouts,
        }

    @staticmethod
    def _aggregate(
        daily: dict,
        inventory_by_day: dict,
        granularity: Granularity,
    ) -> list[dict]:
        grouped = {}
        for day, metrics in sorted(daily.items()):
            bucket_date = trend_bucket_start(day, granularity)
            bucket = grouped.setdefault(
                bucket_date,
                {
                    "date": bucket_date,
                    "revenue": Decimal("0"),
                    "gross_profit": Decimal("0"),
                    "items_sold": Decimal("0"),
                    "order_count": 0,
                    "cogs": Decimal("0"),
                    "purchase_receipts": Decimal("0"),
                    "adjustments": Decimal("0"),
                    "discrepancies": Decimal("0"),
                    "inventory_values": [],
                    "dead_stock_value": Decimal("0"),
                    "stockout_count": 0,
                },
            )
            for key in (
                "revenue",
                "gross_profit",
                "items_sold",
                "order_count",
                "cogs",
                "purchase_receipts",
                "adjustments",
                "discrepancies",
            ):
                bucket[key] += metrics[key]
            inventory = inventory_by_day[day]
            bucket["inventory_values"].append(
                inventory["inventory_value"]
            )
            bucket["inventory_value"] = inventory["inventory_value"]
            bucket["dead_stock_value"] = inventory["dead_stock_value"]
            bucket["stockout_count"] = inventory["stockout_count"]

        result = []
        for bucket in grouped.values():
            average_inventory = sum(
                bucket["inventory_values"],
                Decimal("0"),
            ) / len(bucket["inventory_values"])
            turnover = (
                max(Decimal("0"), bucket["cogs"]) / average_inventory
                if average_inventory > 0
                else Decimal("0")
            )
            result.append(
                {
                    "date": bucket["date"],
                    "revenue": float(bucket["revenue"]),
                    "gross_profit": float(bucket["gross_profit"]),
                    "items_sold": float(bucket["items_sold"]),
                    "order_count": bucket["order_count"],
                    "inventory_value": float(bucket["inventory_value"]),
                    "stockout_count": bucket["stockout_count"],
                    "dead_stock_value": float(
                        bucket["dead_stock_value"]
                    ),
                    "inventory_turnover": float(turnover),
                    "purchase_receipts": float(
                        bucket["purchase_receipts"]
                    ),
                    "adjustments": float(bucket["adjustments"]),
                    "discrepancies": float(bucket["discrepancies"]),
                }
            )
        return result
