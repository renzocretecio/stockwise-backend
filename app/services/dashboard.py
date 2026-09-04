import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.business import Business
from app.models.inventory import (
    InventoryCount,
    InventoryCountItem,
    StockBalance,
    StockMovement,
)
from app.models.product import Product
from app.models.purchase import Purchase, PurchaseItem
from app.models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem

SALE_STATUSES = ("completed", "partially_returned", "returned")
FORECAST_DAYS = 30
FORECAST_METHOD_LABELS = {
    "manual_reorder_point": "Manual reorder settings",
    "recent_moving_average": "Recent sales trend",
    "weighted_moving_average_7_30": (
        "Blended sales trend from the last 7 and 30 days"
    ),
    "weighted_moving_average_7_30_90": (
        "Blended sales trend from the last 7, 30, and 90 days"
    ),
}


@dataclass(frozen=True)
class ForecastCalculation:
    daily_demand: Decimal
    lead_time_demand: Decimal
    recommended_quantity: int
    method: str = "weighted_moving_average_7_30"


def forecast_method_label(method: str) -> str:
    return FORECAST_METHOD_LABELS.get(method, "Sales history trend")


def calculate_reorder(
    average_7d: Decimal,
    average_30d: Decimal,
    current_stock: Decimal,
    incoming_stock: Decimal,
    safety_stock: Decimal,
    lead_time_days: int,
    average_90d: Decimal | None = None,
    history_days: int = 30,
) -> ForecastCalculation:
    if history_days <= 0:
        demand = Decimal("0")
        method = "manual_reorder_point"
    elif history_days < 30:
        demand = average_7d
        method = "recent_moving_average"
    elif history_days < 90 or average_90d is None:
        demand = average_7d * Decimal("0.7")
        demand += average_30d * Decimal("0.3")
        method = "weighted_moving_average_7_30"
    else:
        demand = average_7d * Decimal("0.5")
        demand += average_30d * Decimal("0.3")
        demand += average_90d * Decimal("0.2")
        method = "weighted_moving_average_7_30_90"
    demand = max(Decimal("0"), demand)
    lead_demand = demand * Decimal(lead_time_days)
    shortage = lead_demand + safety_stock
    shortage -= current_stock + incoming_stock
    return ForecastCalculation(
        demand,
        lead_demand,
        max(0, math.ceil(shortage)),
        method,
    )


def count_variance_threshold(history: list[Decimal]) -> Decimal:
    if not history:
        return Decimal("2")
    average = sum(map(abs, history), Decimal("0")) / len(history)
    return max(Decimal("2"), average * Decimal("3"))


def calculate_sales_at_risk(
    daily_demand: Decimal,
    lead_time_days: int,
    available_stock: Decimal,
    incoming_stock: Decimal,
    selling_price: Decimal,
) -> Decimal:
    """Estimate revenue exposed before replenishment can arrive."""
    expected_demand = daily_demand * Decimal(lead_time_days)
    usable_stock = max(
        Decimal("0"),
        available_stock + incoming_stock,
    )
    exposed_units = max(Decimal("0"), expected_demand - usable_stock)
    return exposed_units * max(Decimal("0"), selling_price)


def inventory_age_bucket(days_without_sale: int) -> str:
    if days_without_sale >= 90:
        return "dead_stock"
    if days_without_sale >= 60:
        return "at_risk"
    if days_without_sale >= 30:
        return "slowing"
    return "active"


class DashboardService:
    @staticmethod
    def _bounds(business, target):
        try:
            zone = ZoneInfo(business.timezone)
        except Exception:
            zone = ZoneInfo("UTC")
        start = datetime.combine(target, time.min, zone)
        start = start.astimezone(timezone.utc)
        return start, start + timedelta(days=1), zone

    @staticmethod
    def _daily_sales(business_id, start, end, zone, db):
        daily = defaultdict(lambda: defaultdict(Decimal))
        sales = db.execute(
            select(SaleItem.product_id, SaleItem.quantity, Sale.sale_date)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.business_id == business_id,
                Sale.status.in_(SALE_STATUSES),
                Sale.sale_date >= start,
                Sale.sale_date < end,
            )
        ).all()
        for product_id, quantity, created_at in sales:
            day = created_at.astimezone(zone).date()
            daily[str(product_id)][day] += Decimal(quantity)
        returns = db.execute(
            select(
                SaleReturnItem.product_id,
                SaleReturnItem.quantity,
                SaleReturn.created_at,
            )
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
            .where(
                SaleReturn.business_id == business_id,
                SaleReturn.status == "completed",
                SaleReturn.created_at >= start,
                SaleReturn.created_at < end,
            )
        ).all()
        for product_id, quantity, created_at in returns:
            day = created_at.astimezone(zone).date()
            daily[str(product_id)][day] -= Decimal(quantity)
        return daily

    @staticmethod
    def _revenue(business_id, start, end, db):
        sales = (
            db.execute(
                select(Sale.total_amount).where(
                    Sale.business_id == business_id,
                    Sale.status.in_(SALE_STATUSES),
                    Sale.sale_date >= start,
                    Sale.sale_date < end,
                )
            )
            .scalars()
            .all()
        )
        returns = (
            db.execute(
                select(SaleReturn.refund_amount).where(
                    SaleReturn.business_id == business_id,
                    SaleReturn.status == "completed",
                    SaleReturn.created_at >= start,
                    SaleReturn.created_at < end,
                )
            )
            .scalars()
            .all()
        )
        return sum(map(Decimal, sales), Decimal("0")) - sum(
            map(Decimal, returns), Decimal("0")
        )

    @staticmethod
    def _average(daily, today, period, history_days):
        days = min(period, history_days)
        if not days:
            return Decimal("0")
        total = sum(
            (
                max(
                    Decimal("0"),
                    daily.get(today - timedelta(days=i), Decimal("0")),
                )
                for i in range(days)
            ),
            Decimal("0"),
        )
        return total / days

    @staticmethod
    def get_dashboard(
        business_id: str,
        db: Session,
        stock_days_threshold: int = 7,
    ) -> dict:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one()
        _, _, zone = DashboardService._bounds(business, date.today())
        today = datetime.now(zone).date()
        today_start, today_end, _ = DashboardService._bounds(business, today)
        yesterday_start, _, _ = DashboardService._bounds(
            business, today - timedelta(days=1)
        )
        revenue = DashboardService._revenue(
            business_id, today_start, today_end, db
        )
        prior_revenue = DashboardService._revenue(
            business_id, yesterday_start, today_start, db
        )
        change = None
        if prior_revenue:
            change = float((revenue - prior_revenue) / abs(prior_revenue) * 100)
        rows = db.execute(
            select(Product, StockBalance)
            .join(StockBalance, StockBalance.product_id == Product.id)
            .where(
                Product.business_id == business_id,
                Product.is_active == True,
            )
        ).all()
        daily_sales = DashboardService._daily_sales(
            business_id,
            today_start - timedelta(days=89),
            today_end,
            zone,
            db,
        )
        incoming_rows = db.execute(
            select(PurchaseItem.product_id, PurchaseItem.quantity)
            .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
            .where(
                Purchase.business_id == business_id,
                Purchase.status == "ordered",
            )
        ).all()
        incoming = defaultdict(Decimal)
        for product_id, quantity in incoming_rows:
            incoming[str(product_id)] += Decimal(quantity)

        delivery_dates = db.execute(
            select(Purchase.expected_delivery_date).where(
                Purchase.business_id == business_id,
                Purchase.status == "ordered",
                Purchase.expected_delivery_date.is_not(None),
            )
        ).scalars().all()

        last_sale_rows = db.execute(
            select(
                SaleItem.product_id,
                func.max(Sale.sale_date),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                Sale.business_id == business_id,
                Sale.status.in_(SALE_STATUSES),
            )
            .group_by(SaleItem.product_id)
        ).all()
        last_sale_by_product = dict(last_sale_rows)

        forecasts = []
        below_days_of_stock = 0
        estimated_sales_at_risk = Decimal("0")
        aging = {
            key: {"sku_count": 0, "inventory_value": Decimal("0")}
            for key in ("active", "slowing", "at_risk", "dead_stock")
        }
        efficiency_actions = []
        slow_moving_skus = 0
        perishable_skus = 0
        overstocked_products = 0
        capital_tied_up = Decimal("0")
        for product, balance in rows:
            product_daily = daily_sales.get(str(product.id), {})
            created = product.created_at.astimezone(zone).date()
            history_days = min(90, max(0, (today - created).days + 1))
            averages = {
                period: DashboardService._average(
                    product_daily, today, period, history_days
                )
                for period in (7, 30, 90)
            }
            available = Decimal(balance.quantity)
            available -= Decimal(balance.reserved_quantity)
            calculation = calculate_reorder(
                averages[7],
                averages[30],
                available,
                incoming[str(product.id)],
                Decimal(product.safety_stock),
                product.lead_time_days,
                averages[90],
                history_days,
            )
            stock_on_hand = max(
                Decimal("0"),
                Decimal(balance.quantity),
            )
            inventory_value = stock_on_hand * Decimal(
                balance.average_cost
            )
            last_sale_at = last_sale_by_product.get(product.id)
            activity_at = last_sale_at or product.created_at
            if activity_at.tzinfo is None:
                activity_at = activity_at.replace(tzinfo=timezone.utc)
            activity_date = activity_at.astimezone(zone).date()
            days_without_sale = max((today - activity_date).days, 0)
            classification = inventory_age_bucket(days_without_sale)

            if stock_on_hand > 0:
                aging[classification]["sku_count"] += 1
                aging[classification]["inventory_value"] += inventory_value
                if classification in ("slowing", "at_risk"):
                    slow_moving_skus += 1
                if product.is_perishable:
                    perishable_skus += 1

            target_stock = calculation.lead_time_demand
            target_stock += Decimal(product.safety_stock)
            excess_units = max(
                Decimal("0"),
                max(Decimal("0"), available) - target_stock,
            )
            excess_value = excess_units * Decimal(balance.average_cost)
            is_overstocked = excess_units > 0
            if is_overstocked:
                overstocked_products += 1
                capital_tied_up += excess_value

            action = None
            if classification == "dead_stock":
                action = "Discount, bundle, transfer, or discontinue"
            elif product.is_perishable:
                action = "Review shelf life and prioritize FIFO selling"
            elif classification == "at_risk":
                action = "Promote the product and reduce future orders"
            elif classification == "slowing":
                action = "Review pricing and reduce reorder quantity"
            elif is_overstocked:
                action = "Pause purchasing and review sell-through"

            if stock_on_hand > 0 and action:
                efficiency_actions.append(
                    {
                        "product_id": str(product.id),
                        "product_name": product.name,
                        "sku": product.sku,
                        "classification": classification,
                        "current_stock": float(stock_on_hand),
                        "inventory_value": float(inventory_value),
                        "last_sale_date": activity_date
                        if last_sale_at is not None
                        else None,
                        "days_without_sale": days_without_sale,
                        "excess_units": float(excess_units),
                        "excess_value": float(excess_value),
                        "is_perishable": product.is_perishable,
                        "suggested_action": action,
                    }
                )
            if calculation.daily_demand > 0:
                days_of_stock = max(Decimal("0"), available)
                days_of_stock /= calculation.daily_demand
                if days_of_stock < stock_days_threshold:
                    below_days_of_stock += 1
            estimated_sales_at_risk += calculate_sales_at_risk(
                calculation.daily_demand,
                product.lead_time_days,
                available,
                incoming[str(product.id)],
                Decimal(product.selling_price),
            )
            method_label = forecast_method_label(calculation.method)
            if calculation.recommended_quantity <= 0:
                continue
            confidence = "low"
            if history_days >= 90 and averages[90] > 0:
                confidence = "high"
            elif history_days >= 30 and averages[30] > 0:
                confidence = "medium"
            stockout = None
            if calculation.daily_demand:
                days_left = max(
                    0, math.floor(available / calculation.daily_demand)
                )
                stockout = today + timedelta(days=days_left)
            series = [
                {
                    "date": today - timedelta(days=i),
                    "actual": float(
                        product_daily.get(today - timedelta(days=i), 0)
                    ),
                    "forecast": None,
                }
                for i in range(89, -1, -1)
            ]
            series.extend(
                {
                    "date": today + timedelta(days=i),
                    "actual": None,
                    "forecast": float(calculation.daily_demand),
                }
                for i in range(1, FORECAST_DAYS + 1)
            )
            forecasts.append(
                {
                    "product_id": str(product.id),
                    "product_name": product.name,
                    "sku": product.sku,
                    "supplier_id": str(product.supplier_id)
                    if product.supplier_id
                    else None,
                    "supplier_name": product.supplier.name
                    if product.supplier
                    else None,
                    "current_stock": float(available),
                    "incoming_stock": float(incoming[str(product.id)]),
                    "safety_stock": float(product.safety_stock),
                    "estimated_unit_cost": float(balance.average_cost),
                    "estimated_order_cost": float(
                        Decimal(balance.average_cost)
                        * calculation.recommended_quantity
                    ),
                    "lead_time_days": product.lead_time_days,
                    "average_daily_sales_7d": float(averages[7]),
                    "average_daily_sales_30d": float(averages[30]),
                    "average_daily_sales_90d": float(averages[90]),
                    "forecast_daily_demand": float(calculation.daily_demand),
                    "lead_time_demand": float(calculation.lead_time_demand),
                    "recommended_order_quantity": (
                        calculation.recommended_quantity
                    ),
                    "estimated_stockout_date": stockout,
                    "order_by_date": today,
                    "forecast_period_days": FORECAST_DAYS,
                    "history_days": history_days,
                    "forecast_method": method_label,
                    "confidence": confidence,
                    "recently_out_of_stock": None,
                    "promotion_affected": None,
                    "explanation": [
                        f"Method: {method_label}.",
                        "Lead-time demand is "
                        f"{calculation.lead_time_demand:.2f} units.",
                        "Available and incoming stock are subtracted before "
                        "safety stock is added.",
                    ],
                    "series": series,
                }
            )
        forecasts.sort(
            key=lambda item: item["recommended_order_quantity"],
            reverse=True,
        )
        value = sum(
            (
                Decimal(balance.quantity) * Decimal(balance.average_cost)
                for _, balance in rows
            ),
            Decimal("0"),
        )
        efficiency_actions.sort(
            key=lambda item: (
                {
                    "dead_stock": 3,
                    "at_risk": 2,
                    "slowing": 1,
                    "active": 0,
                }[item["classification"]],
                item["inventory_value"],
            ),
            reverse=True,
        )
        dead_stock_value = aging["dead_stock"]["inventory_value"]
        positive_inventory_value = sum(
            (
                bucket["inventory_value"]
                for bucket in aging.values()
            ),
            Decimal("0"),
        )
        available_rows = [
            (
                product,
                Decimal(balance.quantity)
                - Decimal(balance.reserved_quantity),
            )
            for product, balance in rows
        ]
        out_of_stock_count = sum(
            available <= 0 for _, available in available_rows
        )
        low_stock_count = sum(
            0 < available <= Decimal(product.reorder_point)
            for product, available in available_rows
        )
        return {
            "as_of": today,
            "kpis": {
                "sales_today": float(revenue),
                "sales_yesterday": float(prior_revenue),
                "sales_change_percent": change,
                "inventory_value": float(value),
                "low_stock_count": low_stock_count,
                "out_of_stock_count": out_of_stock_count,
            },
            "inventory_risk": {
                "stock_days_threshold": stock_days_threshold,
                "out_of_stock_skus": out_of_stock_count,
                "low_stock_skus": low_stock_count,
                "below_reorder_point": sum(
                    available < Decimal(product.reorder_point)
                    for product, available in available_rows
                ),
                "below_days_of_stock": below_days_of_stock,
                "pending_reorder_recommendations": len(forecasts),
                "expected_deliveries_today": sum(
                    delivery_date == today
                    for delivery_date in delivery_dates
                ),
                "late_purchase_orders": sum(
                    delivery_date < today
                    for delivery_date in delivery_dates
                ),
                "estimated_sales_at_risk": float(
                    estimated_sales_at_risk
                ),
            },
            "inventory_efficiency": {
                "dead_stock_value": float(dead_stock_value),
                "dead_stock_percentage": float(
                    dead_stock_value / positive_inventory_value * 100
                    if positive_inventory_value > 0
                    else 0
                ),
                "slow_moving_skus": slow_moving_skus,
                "perishable_skus": perishable_skus,
                "overstocked_products": overstocked_products,
                "capital_tied_up": float(capital_tied_up),
                "aging_buckets": [
                    {
                        "key": key,
                        "sku_count": bucket["sku_count"],
                        "inventory_value": float(
                            bucket["inventory_value"]
                        ),
                    }
                    for key, bucket in aging.items()
                ],
                "actions": efficiency_actions[:10],
            },
            "forecasts": forecasts[:10],
            "anomalies": DashboardService._anomalies(
                business_id, rows, today_start, db
            )[:10],
        }

    @staticmethod
    def _anomalies(business_id, rows, today_start, db):
        names = {str(product.id): product.name for product, _ in rows}
        anomalies = []
        for product, balance in rows:
            if Decimal(balance.quantity) < 0:
                anomalies.append(
                    {
                        "id": f"negative-{product.id}",
                        "product_id": str(product.id),
                        "product_name": product.name,
                        "anomaly_type": "negative_stock",
                        "severity": "high",
                        "quantity": float(balance.quantity),
                        "title": f"{product.name} has negative stock",
                        "detail": (
                            "Verify sales, returns, counts, or data entry."
                        ),
                        "occurred_at": balance.updated_at.isoformat(),
                    }
                )
        count_rows = db.execute(
            select(InventoryCountItem, InventoryCount)
            .join(
                InventoryCount,
                InventoryCount.id == InventoryCountItem.inventory_count_id,
            )
            .where(
                InventoryCount.business_id == business_id,
                InventoryCount.status == "finalized",
                InventoryCountItem.counted_quantity.is_not(None),
            )
            .order_by(InventoryCount.finalized_at.desc())
        ).all()
        grouped = defaultdict(list)
        for item, count in count_rows:
            grouped[str(item.product_id)].append((item, count))
        for product_id, counts in grouped.items():
            if product_id not in names:
                continue
            item, count = counts[0]
            variance = Decimal(item.counted_quantity)
            variance -= Decimal(item.expected_quantity)
            history = [
                Decimal(old.counted_quantity) - Decimal(old.expected_quantity)
                for old, _ in counts[1:]
            ]
            threshold = count_variance_threshold(history)
            if abs(variance) <= threshold:
                continue
            expected = abs(Decimal(item.expected_quantity))
            percentage = abs(variance) / expected * 100 if expected else None
            anomalies.append(
                {
                    "id": f"count-{item.id}",
                    "product_id": product_id,
                    "product_name": names[product_id],
                    "anomaly_type": "count_variance",
                    "severity": "high"
                    if abs(variance) >= threshold * 2
                    else "medium",
                    "quantity": float(variance),
                    "title": f"Unusual discrepancy for {names[product_id]}",
                    "detail": (
                        "Verify count, spoilage, returns, or data entry."
                    ),
                    "occurred_at": count.finalized_at.isoformat()
                    if count.finalized_at
                    else None,
                    "historical_average_variance": float(
                        sum(map(abs, history), Decimal("0")) / len(history)
                    )
                    if history
                    else None,
                    "anomaly_threshold": float(threshold),
                    "variance_percentage": float(percentage)
                    if percentage is not None
                    else None,
                    "historical_count": len(history),
                }
            )
        adjustments = (
            db.execute(
                select(StockMovement).where(
                    StockMovement.business_id == business_id,
                    StockMovement.movement_type == "adjustment",
                    StockMovement.created_at >= today_start - timedelta(days=7),
                )
            )
            .scalars()
            .all()
        )
        for movement in adjustments:
            product_id = str(movement.product_id)
            if abs(Decimal(movement.quantity)) < 10 or product_id not in names:
                continue
            anomalies.append(
                {
                    "id": f"adjustment-{movement.id}",
                    "product_id": product_id,
                    "product_name": names[product_id],
                    "anomaly_type": "large_adjustment",
                    "severity": "medium",
                    "quantity": float(movement.quantity),
                    "title": f"Large adjustment for {names[product_id]}",
                    "detail": movement.reason
                    or "Verify the adjustment and supporting count.",
                    "occurred_at": movement.created_at.isoformat(),
                }
            )
        rank = {"high": 2, "medium": 1}
        return sorted(
            anomalies,
            key=lambda item: (rank[item["severity"]], abs(item["quantity"])),
            reverse=True,
        )
