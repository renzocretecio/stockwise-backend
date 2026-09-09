import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.business import Business
from app.schemas.intelligence import IntelligenceMessage
from app.services.communication import (
    GroqCommunicationService,
    communication_enabled,
)
from app.services.dashboard import DashboardService
from app.services.entitlements import EntitlementService
from app.services.report import ReportService


logger = logging.getLogger(__name__)


class IntelligenceService:
    @staticmethod
    def with_business_context(
        business_id: str,
        context: dict,
        db: Session,
    ) -> dict:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()
        if not business:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found",
            )
        return {
            **context,
            "business": {
                "currency_code": business.currency_code,
                "timezone": business.timezone,
            },
        }

    @staticmethod
    def fallback(intent: str, context: dict) -> IntelligenceMessage:
        if intent == "report_summary":
            report = str(context.get("report", "report")).replace("_", " ")
            metrics = context.get("metrics", {})
            facts = [
                f"{key.replace('_', ' ').title()}: {value}"
                for key, value in list(metrics.items())[:4]
            ]
            return IntelligenceMessage(
                answer=(
                    f"Your {report} summary is ready for "
                    f"{context.get('period', 'the selected period')}."
                ),
                facts=facts,
                limitations=[
                    "AI narration is unavailable; review the calculated facts."
                ],
            )
        if intent == "reorder_products":
            forecasts = context.get("forecasts", [])
            if context.get("forecast"):
                forecasts = [context["forecast"]]
            if not forecasts:
                answer = "No products currently have a calculated reorder need."
                actions = []
            else:
                first = forecasts[0]
                answer = (
                    f"Review {first['product_name']} first. The calculated "
                    f"order recommendation is "
                    f"{first['recommended_order_quantity']} units."
                )
                actions = ["Review the forecast before creating a purchase."]
            return IntelligenceMessage(
                answer=answer,
                facts=[],
                estimates=[],
                recommended_actions=actions,
                limitations=["Forecasts depend on recorded sales accuracy."],
            )
        if intent == "inventory_anomalies":
            anomalies = context.get("anomalies", [])
            if context.get("anomaly"):
                anomalies = [context["anomaly"]]
            answer = f"{len(anomalies)} inventory anomalies require review."
            return IntelligenceMessage(
                answer=answer,
                facts=[item["title"] for item in anomalies[:5]],
                recommended_actions=["Investigate the underlying movements."],
            )
        return IntelligenceMessage(
            answer="The requested analytics are available in the attached facts.",
            facts=["Review the structured context for exact values."],
            limitations=["AI narration is unavailable; no facts were inferred."],
        )

    @staticmethod
    async def communicate(
        intent: str,
        context: dict,
        task: str,
        business_id: str,
        db: Session,
    ) -> tuple[str, str | None, IntelligenceMessage]:
        if communication_enabled():
            EntitlementService.consume_ai_insight(business_id, db)
            db.commit()
            try:
                communicator = GroqCommunicationService()
                message = await communicator.explain(task, context)
                return "groq", communicator.model, message
            except Exception:
                logger.warning("Groq narration failed; using template", exc_info=True)
                try:
                    EntitlementService.refund_ai_insight(business_id, db)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("Unable to refund the AI insight quota")
        return "template", None, IntelligenceService.fallback(intent, context)

    @staticmethod
    async def explain_forecast(
        business_id: str, product_id: str, db: Session
    ) -> dict:
        dashboard = DashboardService.get_dashboard(business_id, db)
        forecast = next(
            (
                item
                for item in dashboard["forecasts"]
                if item["product_id"] == product_id
            ),
            None,
        )
        if not forecast:
            raise HTTPException(404, "Forecast recommendation not found")
        context = {
            "forecast": {
                key: value
                for key, value in forecast.items()
                if key != "series"
            }
        }
        context = IntelligenceService.with_business_context(
            business_id,
            context,
            db,
        )
        provider, model, message = await IntelligenceService.communicate(
            "reorder_products",
            context,
            "Explain why this order quantity was recommended.",
            business_id,
            db,
        )
        return {
            "intent": "forecast_explanation",
            "provider": provider,
            "model": model,
            "message": message,
            "context": context,
        }

    @staticmethod
    async def explain_anomaly(
        business_id: str, anomaly_id: str, db: Session
    ) -> dict:
        dashboard = DashboardService.get_dashboard(business_id, db)
        anomaly = next(
            (
                item
                for item in dashboard["anomalies"]
                if item["id"] == anomaly_id
            ),
            None,
        )
        if not anomaly:
            raise HTTPException(404, "Inventory anomaly not found")
        context = IntelligenceService.with_business_context(
            business_id,
            {"anomaly": anomaly},
            db,
        )
        provider, model, message = await IntelligenceService.communicate(
            "inventory_anomalies",
            context,
            "Explain why this inventory anomaly was flagged.",
            business_id,
            db,
        )
        return {
            "intent": "anomaly_explanation",
            "provider": provider,
            "model": model,
            "message": message,
            "context": context,
        }

    @staticmethod
    async def summarize_report(
        business_id: str,
        report: str,
        days: int,
        db: Session,
    ) -> dict:
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()
        if not business:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found",
            )

        timezone_name = business.timezone or "UTC"
        try:
            report_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            report_timezone = ZoneInfo("UTC")

        period_end = datetime.now(report_timezone).date()
        period_start = period_end - timedelta(days=days - 1)
        period_label = f"{period_start.isoformat()} to {period_end.isoformat()}"
        analytics = IntelligenceService._build_report_summary_context(
            business_id=business_id,
            report=report,
            days=days,
            period_start=period_start,
            period_end=period_end,
            timezone_name=timezone_name,
            db=db,
        )
        context = IntelligenceService.with_business_context(
            business_id,
            {
                "report": report,
                "period": period_label,
                **analytics,
            },
            db,
        )
        provider, model, message = await IntelligenceService.communicate(
            "report_summary",
            context,
            (
                f"Write a concise 2-to-4 sentence owner-ready summary of "
                f"this {report.replace('_', ' ')} report. Mention the "
                "strongest recorded result, the clearest risk, and only "
                "compare periods when comparison metrics are supplied."
            ),
            business_id,
            db,
        )
        return {
            "intent": "report_summary",
            "provider": provider,
            "model": model,
            "message": message,
            "context": context,
        }

    @staticmethod
    def _build_report_summary_context(
        *,
        business_id: str,
        report: str,
        days: int,
        period_start: date,
        period_end: date,
        timezone_name: str,
        db: Session,
    ) -> dict:
        if report == "sales":
            current = ReportService.get_sales_report(
                business_id,
                days,
                db,
                start_date=period_start,
                end_date=period_end,
                timezone_name=timezone_name,
            )
            previous_end = period_start - timedelta(days=1)
            previous_start = previous_end - timedelta(days=days - 1)
            previous = ReportService.get_sales_report(
                business_id,
                days,
                db,
                start_date=previous_start,
                end_date=previous_end,
                timezone_name=timezone_name,
            )
            current_summary = current["summary"]
            previous_revenue = previous["summary"]["total_revenue"]
            return {
                "metrics": {
                    "revenue": current_summary["total_revenue"],
                    "gross_profit": current_summary["total_profit"],
                    "sales_count": current_summary["total_sales"],
                    "items_sold": current_summary["total_items_sold"],
                    "returns": current_summary["return_count"],
                    "return_amount": current_summary["return_amount"],
                },
                "top_products": [
                    {
                        "name": product["product_name"],
                        "units_sold": product["quantity_sold"],
                        "revenue": product["revenue"],
                    }
                    for product in current["top_products"][:5]
                ],
                "slow_products": [
                    {
                        "name": product["product_name"],
                        "days_without_sale": product["days_without_sale"],
                        "inventory_value": product["inventory_value"],
                    }
                    for product in current["slow_products"][:5]
                ],
                "comparison_to_previous_period": {
                    "revenue_percent": IntelligenceService._percent_change(
                        current_summary["total_revenue"],
                        previous_revenue,
                    ),
                },
            }

        if report == "purchases":
            current = ReportService.get_purchase_report(business_id, days, db)
            return {
                "metrics": current["summary"],
                "top_suppliers": [
                    {
                        "name": supplier["supplier_name"],
                        "total_spent": supplier["total_spent"],
                        "purchases_count": supplier["purchases_count"],
                    }
                    for supplier in current["by_supplier"][:5]
                ],
            }

        if report == "inventory":
            current = ReportService.get_inventory_report(business_id, db)
            return {
                "metrics": current["summary"],
                "top_categories": [
                    {
                        "name": category["category"],
                        "stock_value": category["stock_value"],
                        "units": category["total_units"],
                    }
                    for category in current["by_category"][:5]
                ],
            }

        if report == "profit":
            current = ReportService.get_profit_report(business_id, days, db)
            return {
                "metrics": current["summary"],
                "top_products": [
                    {
                        "name": product["product_name"],
                        "revenue": product["revenue"],
                        "gross_profit": product["profit"],
                        "gross_margin_percent": product["margin_percent"],
                    }
                    for product in current["by_product"][:5]
                ],
            }

        if report == "low_stock":
            current = ReportService.get_low_stock_report(business_id, db)
            out_of_stock = sum(
                item["status"] == "out_of_stock"
                for item in current["items"]
            )
            return {
                "metrics": {
                    "products_requiring_attention": current["total_items"],
                    "out_of_stock": out_of_stock,
                    "low_stock": current["total_items"] - out_of_stock,
                },
                "highest_priority_products": [
                    {
                        "name": item["product_name"],
                        "status": item["status"],
                        "on_hand": item["quantity"],
                        "reorder_point": item["reorder_point"],
                        "supplier": item["supplier_name"],
                    }
                    for item in current["items"][:5]
                ],
            }

        current = ReportService.get_stock_movement_report(
            business_id,
            days,
            db,
        )
        return {
            "metrics": {"total_movements": current["total_movements"]},
            "movement_types": [
                {
                    "type": item["movement_type"],
                    "records": item["total_movements"],
                    "net_quantity_change": item["total_quantity_change"],
                }
                for item in current["by_type"][:8]
            ],
        }

    @staticmethod
    def _percent_change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round(((current - previous) / abs(previous)) * 100, 1)
