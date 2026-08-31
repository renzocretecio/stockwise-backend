import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

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
    def get_dashboard(business_id: str, db: Session) -> dict:
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

        forecasts = []
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
        return {
            "as_of": today,
            "kpis": {
                "sales_today": float(revenue),
                "sales_yesterday": float(prior_revenue),
                "sales_change_percent": change,
                "inventory_value": float(value),
                "low_stock_count": sum(
                    1
                    for product, balance in rows
                    if 0
                    < Decimal(balance.quantity)
                    <= Decimal(product.reorder_point)
                ),
                "out_of_stock_count": sum(
                    Decimal(balance.quantity) <= 0 for _, balance in rows
                ),
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
