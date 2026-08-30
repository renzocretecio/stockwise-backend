from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.config.settings import settings
from app.models.briefing import InventoryBriefing, InventoryRecommendation
from app.models.business import Business
from app.models.inventory import (
    InventoryCount,
    InventoryCountItem,
    StockBalance,
)
from app.models.product import Product
from app.models.purchase import Purchase, PurchaseItem
from app.models.sale import Sale, SaleItem
from app.schemas.briefing import BriefingNarration
from app.services.communication import GeminiCommunicationService
from app.services.dashboard import DashboardService


@dataclass
class ProductMetrics:
    product_id: str
    product_name: str
    current_stock: Decimal
    reorder_point: Decimal
    safety_stock: Decimal
    average_cost: Decimal
    average_daily_sales_7d: Decimal
    average_daily_sales_30d: Decimal
    sales_yesterday: Decimal
    sales_change_percent: Decimal | None
    incoming_stock: Decimal
    lead_time_days: int
    days_since_last_sale: int | None
    latest_count_variance: Decimal | None


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


class TemplateNarrator:
    provider = "template"
    model = None

    async def generate(self, recommendations: list[dict]) -> BriefingNarration:
        if not recommendations:
            return BriefingNarration(
                headline="Inventory is stable today",
                summary=[
                    "No urgent inventory issues were identified from the "
                    "available data.",
                    "Review the dashboard for routine stock levels.",
                    "Verify that recent sales and counts are complete.",
                ],
            )
        summary = [
            f"{item['title']}: {item['recommended_action']}"
            for item in recommendations[:3]
        ]
        while len(summary) < 3:
            summary.append(
                "No additional urgent inventory action was identified."
            )
        item_count = len(recommendations)
        suffix = "s" if item_count != 1 else ""
        headline = f"{item_count} inventory item{suffix} need attention"
        return BriefingNarration(headline=headline, summary=summary)


class GeminiNarrator:
    provider = "gemini"

    def __init__(self):
        self.model = settings.GEMINI_MODEL

    async def generate(
        self,
        recommendations: list[dict],
        dashboard_context: dict | None = None,
    ) -> BriefingNarration:
        communicator = GeminiCommunicationService()
        return await communicator.create_briefing(
            {
                "recommendations": recommendations[:5],
                "business_metrics": (
                    dashboard_context.get("kpis", {})
                    if dashboard_context
                    else {}
                ),
                "demand_forecasts": (
                    [
                        {
                            key: value
                            for key, value in forecast.items()
                            if key != "series"
                        }
                        for forecast in dashboard_context.get(
                            "forecasts", []
                        )[:3]
                    ]
                    if dashboard_context
                    else []
                ),
                "inventory_anomalies": (
                    dashboard_context.get("anomalies", [])[:3]
                    if dashboard_context
                    else []
                ),
            }
        )


class BriefingService:
    METRICS_VERSION = "v1"

    @staticmethod
    def _period(
        business: Business, target_date: date
    ) -> tuple[datetime, datetime]:
        try:
            zone = ZoneInfo(business.timezone)
        except Exception:
            zone = ZoneInfo("UTC")
        start = datetime.combine(target_date, time.min, zone)
        return start.astimezone(timezone.utc), (
            start + timedelta(days=1)
        ).astimezone(timezone.utc)

    @staticmethod
    def _collect_metrics(
        business: Business, target_date: date, db: Session
    ) -> list[ProductMetrics]:
        day_start, day_end = BriefingService._period(business, target_date)
        start_30 = day_start - timedelta(days=29)
        products = db.execute(
            select(Product, StockBalance)
            .join(StockBalance, StockBalance.product_id == Product.id)
            .where(
                Product.business_id == business.id, Product.is_active == True
            )
        ).all()
        result = []
        valid_sale_statuses = ["completed", "partially_returned", "returned"]
        for product, balance in products:
            sales = db.execute(
                select(SaleItem.quantity, Sale.sale_date)
                .join(Sale, Sale.id == SaleItem.sale_id)
                .where(
                    Sale.business_id == business.id,
                    Sale.status.in_(valid_sale_statuses),
                    SaleItem.product_id == product.id,
                    Sale.sale_date >= start_30,
                    Sale.sale_date < day_end,
                )
            ).all()
            total_30 = sum(
                (Decimal(quantity) for quantity, _ in sales), Decimal("0")
            )
            total_7 = sum(
                (
                    Decimal(quantity)
                    for quantity, created_at in sales
                    if created_at >= day_start - timedelta(days=6)
                ),
                Decimal("0"),
            )
            yesterday = sum(
                (
                    Decimal(quantity)
                    for quantity, created_at in sales
                    if day_start <= created_at < day_end
                ),
                Decimal("0"),
            )
            prior_7_start = day_start - timedelta(days=7)
            prior_7_total = sum(
                (
                    Decimal(quantity)
                    for quantity, created_at in sales
                    if prior_7_start <= created_at < day_start
                ),
                Decimal("0"),
            )
            prior_daily_average = prior_7_total / Decimal("7")
            sales_change = None
            if prior_daily_average > 0:
                sales_change = (
                    (yesterday - prior_daily_average)
                    / prior_daily_average
                    * Decimal("100")
                )
            last_sale = max(
                (created_at for _, created_at in sales), default=None
            )
            incoming = db.execute(
                select(func.coalesce(func.sum(PurchaseItem.quantity), 0))
                .join(Purchase, Purchase.id == PurchaseItem.purchase_id)
                .where(
                    Purchase.business_id == business.id,
                    Purchase.status == "ordered",
                    PurchaseItem.product_id == product.id,
                )
            ).scalar_one()
            count_row = db.execute(
                select(InventoryCountItem)
                .join(
                    InventoryCount,
                    InventoryCount.id == InventoryCountItem.inventory_count_id,
                )
                .where(
                    InventoryCount.business_id == business.id,
                    InventoryCount.status == "finalized",
                    InventoryCountItem.product_id == product.id,
                    InventoryCountItem.counted_quantity.is_not(None),
                )
                .order_by(InventoryCount.finalized_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            variance = (
                None
                if not count_row
                else Decimal(count_row.counted_quantity)
                - Decimal(count_row.expected_quantity)
            )
            result.append(
                ProductMetrics(
                    product_id=str(product.id),
                    product_name=product.name,
                    current_stock=Decimal(balance.quantity)
                    - Decimal(balance.reserved_quantity),
                    reorder_point=Decimal(product.reorder_point),
                    safety_stock=Decimal(product.safety_stock),
                    average_cost=Decimal(balance.average_cost),
                    average_daily_sales_7d=total_7 / Decimal("7"),
                    average_daily_sales_30d=total_30 / Decimal("30"),
                    sales_yesterday=yesterday,
                    sales_change_percent=sales_change,
                    incoming_stock=Decimal(incoming),
                    lead_time_days=product.lead_time_days,
                    days_since_last_sale=(
                        target_date
                        - last_sale.astimezone(
                            ZoneInfo(business.timezone)
                        ).date()
                    ).days
                    if last_sale
                    else None,
                    latest_count_variance=variance,
                )
            )
        return result

    @staticmethod
    def _recommend(
        metrics: list[ProductMetrics],
        business: Business,
        target_date: date,
        db: Session,
    ) -> list[dict]:
        recommendations = []
        for item in metrics:
            velocity = (
                item.average_daily_sales_7d
                if item.average_daily_sales_7d > 0
                else item.average_daily_sales_30d
            )
            days_left = item.current_stock / velocity if velocity > 0 else None
            base = {"product_id": item.product_id, "purchase_id": None}
            if item.sales_change_percent is not None and abs(
                item.sales_change_percent
            ) >= Decimal("30"):
                direction = (
                    "increased"
                    if item.sales_change_percent > 0
                    else "decreased"
                )
                change = item.sales_change_percent.quantize(Decimal("1"))
                recommendations.append(
                    {
                        **base,
                        "type": "sales_change",
                        "priority": "medium",
                        "priority_score": 60,
                        "confidence": "medium",
                        "title": (f"{item.product_name} sales {direction}"),
                        "recommended_action": (
                            "Verify the change and review replenishment needs"
                        ),
                        "evidence": [
                            f"Yesterday's sales were {item.sales_yesterday}",
                            "Change from the prior seven-day daily average is "
                            f"{change}%",
                        ],
                        "metrics": {
                            "sales_yesterday": item.sales_yesterday,
                            "sales_change_percent": (item.sales_change_percent),
                        },
                        "rule_id": "sales_change_v1",
                    }
                )
            if days_left is not None and days_left <= item.lead_time_days:
                recommendations.append(
                    {
                        **base,
                        "type": "stockout_risk",
                        "priority": "high",
                        "priority_score": 90,
                        "confidence": "medium",
                        "title": f"{item.product_name} may run out soon",
                        "recommended_action": (
                            "Review reorder quantity or expedite an ordered "
                            "delivery"
                        ),
                        "evidence": [
                            f"Available stock is {item.current_stock}",
                            "Estimated coverage is "
                            f"{days_left.quantize(Decimal('0.1'))} days",
                            f"Lead time is {item.lead_time_days} days",
                            "Inventory value at risk is "
                            f"{item.current_stock * item.average_cost}",
                        ],
                        "metrics": {
                            "current_stock": item.current_stock,
                            "estimated_days_left": days_left,
                            "lead_time_days": item.lead_time_days,
                            "incoming_stock": item.incoming_stock,
                            "stock_value_at_risk": (
                                item.current_stock * item.average_cost
                            ),
                        },
                        "rule_id": "stockout_risk_v1",
                    }
                )
            elif item.current_stock <= item.reorder_point:
                recommendations.append(
                    {
                        **base,
                        "type": "low_stock",
                        "priority": "high"
                        if item.current_stock <= 0
                        else "medium",
                        "priority_score": 80 if item.current_stock <= 0 else 65,
                        "confidence": "high",
                        "title": f"{item.product_name} is low on stock",
                        "recommended_action": "Review replenishment needs",
                        "evidence": [
                            f"Available stock is {item.current_stock}",
                            f"Reorder point is {item.reorder_point}",
                        ],
                        "metrics": {
                            "current_stock": item.current_stock,
                            "reorder_point": item.reorder_point,
                        },
                        "rule_id": "low_stock_v1",
                    }
                )
            if item.current_stock > 0 and (
                item.days_since_last_sale is None
                or item.days_since_last_sale >= 90
            ):
                recommendations.append(
                    {
                        **base,
                        "type": "dead_stock",
                        "priority": "medium",
                        "priority_score": 50,
                        "confidence": "medium",
                        "title": f"{item.product_name} may be dead stock",
                        "recommended_action": (
                            "Review pricing, bundling, or discontinuation"
                        ),
                        "evidence": [
                            "No recorded sale in at least 90 days"
                            if item.days_since_last_sale
                            else "No recorded sales history",
                            f"Stock on hand is {item.current_stock}",
                        ],
                        "metrics": {
                            "current_stock": item.current_stock,
                            "days_since_last_sale": item.days_since_last_sale,
                            "stock_value": item.current_stock
                            * item.average_cost,
                        },
                        "rule_id": "dead_stock_v1",
                    }
                )
            elif velocity > 0 and item.current_stock / velocity >= Decimal(
                "180"
            ):
                coverage = item.current_stock / velocity
                recommendations.append(
                    {
                        **base,
                        "type": "overstock",
                        "priority": "medium",
                        "priority_score": 45,
                        "confidence": "medium",
                        "title": f"{item.product_name} may be overstocked",
                        "recommended_action": (
                            "Review future purchasing and sell-through plans"
                        ),
                        "evidence": [
                            "Estimated stock coverage is "
                            f"{coverage.quantize(Decimal('1'))} days",
                        ],
                        "metrics": {
                            "current_stock": item.current_stock,
                            "estimated_days_left": coverage,
                            "stock_value": (
                                item.current_stock * item.average_cost
                            ),
                        },
                        "rule_id": "overstock_v1",
                    }
                )
            if item.latest_count_variance is not None and abs(
                item.latest_count_variance
            ) > Decimal("2"):
                recommendations.append(
                    {
                        **base,
                        "type": "count_variance",
                        "priority": "high",
                        "priority_score": 75,
                        "confidence": "medium",
                        "title": f"Verify the {item.product_name} count",
                        "recommended_action": (
                            "Recount the product and review recent movements"
                        ),
                        "evidence": [
                            "Latest physical-count variance is "
                            f"{item.latest_count_variance} units"
                        ],
                        "metrics": {"variance": item.latest_count_variance},
                        "rule_id": "count_variance_v1",
                    }
                )
        ordered = (
            db.execute(
                select(Purchase).where(
                    Purchase.business_id == business.id,
                    Purchase.status == "ordered",
                )
            )
            .scalars()
            .all()
        )
        for purchase in ordered:
            lead_time = (
                purchase.supplier.lead_time_days if purchase.supplier else 3
            )
            age = (
                target_date
                - (purchase.ordered_at or purchase.created_at)
                .astimezone(ZoneInfo(business.timezone))
                .date()
            ).days
            if age > lead_time:
                reference = purchase.reference_number or str(purchase.id)[:8]
                recommendations.append(
                    {
                        "product_id": None,
                        "purchase_id": str(purchase.id),
                        "type": "overdue_purchase",
                        "priority": "high",
                        "priority_score": 85,
                        "confidence": "high",
                        "title": f"Purchase {reference} may be overdue",
                        "recommended_action": (
                            "Contact the supplier and confirm the delivery date"
                        ),
                        "evidence": [
                            f"Awaiting receipt for {age} days",
                            f"Supplier lead time is {lead_time} days",
                        ],
                        "metrics": {
                            "days_waiting": age,
                            "lead_time_days": lead_time,
                        },
                        "rule_id": "overdue_purchase_v1",
                    }
                )
        return sorted(
            recommendations,
            key=lambda item: item["priority_score"],
            reverse=True,
        )

    @staticmethod
    async def generate(
        business_id: str, user_id: str, db: Session, force: bool = False
    ) -> dict:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()
        if not business:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found",
            )
        today = datetime.now(ZoneInfo(business.timezone)).date()
        existing = db.execute(
            select(InventoryBriefing).where(
                InventoryBriefing.business_id == business.id,
                InventoryBriefing.briefing_date == today,
            )
        ).scalar_one_or_none()
        if existing and not force:
            return BriefingService.format(existing)
        if existing:
            db.delete(existing)
            db.flush()
        recommendations = BriefingService._recommend(
            BriefingService._collect_metrics(
                business, today - timedelta(days=1), db
            ),
            business,
            today,
            db,
        )
        template = TemplateNarrator()
        narrator = (
            GeminiNarrator()
            if settings.NARRATOR_PROVIDER == "gemini"
            and settings.GEMINI_API_KEY
            else template
        )
        provider, model, error_message = narrator.provider, narrator.model, None
        try:
            dashboard_context = DashboardService.get_dashboard(
                business_id, db
            )
            if isinstance(narrator, GeminiNarrator):
                narration = await narrator.generate(
                    recommendations, dashboard_context
                )
            else:
                narration = await narrator.generate(recommendations)
        except Exception as exc:
            provider, model, error_message = "template", None, str(exc)[:1000]
            narration = await template.generate(recommendations)
        briefing = InventoryBriefing(
            business_id=business.id,
            briefing_date=today,
            status="generated",
            headline=narration.headline,
            summary=narration.summary,
            narrator_provider=provider,
            narrator_model=model,
            metrics_version=BriefingService.METRICS_VERSION,
            error_message=error_message,
            generated_by=user_id,
        )
        db.add(briefing)
        db.flush()
        for item in recommendations:
            db.add(
                InventoryRecommendation(
                    briefing_id=briefing.id,
                    product_id=item["product_id"],
                    purchase_id=item["purchase_id"],
                    recommendation_type=item["type"],
                    priority=item["priority"],
                    priority_score=item["priority_score"],
                    confidence=item["confidence"],
                    title=item["title"],
                    recommended_action=item["recommended_action"],
                    evidence=item["evidence"],
                    metrics={
                        key: _json_value(value)
                        for key, value in item["metrics"].items()
                    },
                    rule_id=item["rule_id"],
                )
            )
        db.commit()
        db.refresh(briefing)
        return BriefingService.format(briefing)

    @staticmethod
    def get_today(business_id: str, db: Session) -> dict | None:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()
        if not business:
            return None
        today = datetime.now(ZoneInfo(business.timezone)).date()
        briefing = db.execute(
            select(InventoryBriefing).where(
                InventoryBriefing.business_id == business.id,
                InventoryBriefing.briefing_date == today,
            )
        ).scalar_one_or_none()
        return BriefingService.format(briefing) if briefing else None

    @staticmethod
    def format(briefing: InventoryBriefing) -> dict:
        items = sorted(
            briefing.recommendations,
            key=lambda item: item.priority_score,
            reverse=True,
        )
        return {
            "id": str(briefing.id),
            "briefing_date": briefing.briefing_date,
            "status": briefing.status,
            "headline": briefing.headline,
            "summary": briefing.summary,
            "narrator_provider": briefing.narrator_provider,
            "narrator_model": briefing.narrator_model,
            "generated_at": briefing.generated_at,
            "recommendations": [
                {
                    "id": str(item.id),
                    "product_id": str(item.product_id)
                    if item.product_id
                    else None,
                    "purchase_id": str(item.purchase_id)
                    if item.purchase_id
                    else None,
                    "type": item.recommendation_type,
                    "priority": item.priority,
                    "priority_score": item.priority_score,
                    "confidence": item.confidence,
                    "title": item.title,
                    "recommended_action": item.recommended_action,
                    "evidence": item.evidence,
                    "metrics": item.metrics,
                    "rule_id": item.rule_id,
                    "dismissed_at": item.dismissed_at,
                    "resolved_at": item.resolved_at,
                }
                for item in items
            ],
        }
