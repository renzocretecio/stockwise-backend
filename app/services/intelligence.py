from typing import Callable

from fastapi import HTTPException, status
from sqlmodel import Session

from app.schemas.intelligence import IntelligenceMessage
from app.services.communication import (
    GeminiCommunicationService,
    communication_enabled,
)
from app.services.dashboard import DashboardService
from app.services.report import ReportService


class IntelligenceService:
    INTENT_KEYWORDS = {
        "reorder_products": ("reorder", "order", "run out", "stockout"),
        "slow_moving_products": (
            "not selling",
            "slow moving",
            "slow-moving",
            "dead stock",
            "tied up",
        ),
        "inventory_anomalies": (
            "anomal",
            "loss",
            "discrep",
            "variance",
            "unusual stock",
        ),
        "top_selling_products": ("best selling", "top selling", "top product"),
        "sales_performance": ("sales", "revenue", "lower this week"),
        "profitability": ("profit", "margin", "profitable"),
        "supplier_performance": ("supplier", "delivery time", "lead time"),
    }

    @staticmethod
    def classify(question: str) -> str:
        normalized = question.casefold()
        for intent, keywords in IntelligenceService.INTENT_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return intent
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "I can answer questions about reordering, slow-moving stock, "
                "anomalies, sales, profit, products, and suppliers."
            ),
        )

    @staticmethod
    def context_for_intent(
        business_id: str, intent: str, db: Session
    ) -> dict:
        dashboard = DashboardService.get_dashboard(business_id, db)
        if intent == "reorder_products":
            forecasts = [
                {
                    key: value
                    for key, value in forecast.items()
                    if key != "series"
                }
                for forecast in dashboard["forecasts"][:5]
            ]
            return {"forecasts": forecasts}
        if intent == "inventory_anomalies":
            return {"anomalies": dashboard["anomalies"][:10]}
        if intent == "slow_moving_products":
            inventory = ReportService.get_inventory_report(business_id, db)
            return {
                "inventory_summary": inventory["summary"],
                "limitation": (
                    "Current analytics identify dead stock in the daily "
                    "briefing; a complete ranked slow-moving list is not yet "
                    "available in this endpoint."
                ),
            }
        if intent == "top_selling_products":
            report = ReportService.get_sales_report(business_id, 30, db)
            return {"period_days": 30, "products": report["top_products"]}
        if intent == "sales_performance":
            return ReportService.get_sales_report(business_id, 30, db)
        if intent == "profitability":
            return ReportService.get_profit_report(business_id, 30, db)
        if intent == "supplier_performance":
            return ReportService.get_purchase_report(business_id, 90, db)
        return {}

    @staticmethod
    def fallback(intent: str, context: dict) -> IntelligenceMessage:
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
            limitations=["Gemini narration is unavailable; no facts were inferred."],
        )

    @staticmethod
    async def communicate(
        intent: str, context: dict, task: str
    ) -> tuple[str, str | None, IntelligenceMessage]:
        if communication_enabled():
            try:
                communicator = GeminiCommunicationService()
                message = await communicator.explain(task, context)
                return "gemini", communicator.model, message
            except Exception:
                pass
        return "template", None, IntelligenceService.fallback(intent, context)

    @staticmethod
    async def ask(
        business_id: str, question: str, db: Session
    ) -> dict:
        intent = IntelligenceService.classify(question)
        context = IntelligenceService.context_for_intent(
            business_id, intent, db
        )
        provider, model, message = await IntelligenceService.communicate(
            intent,
            context,
            f"Answer this approved business question: {question}",
        )
        return {
            "intent": intent,
            "provider": provider,
            "model": model,
            "message": message,
            "context": context,
        }

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
        provider, model, message = await IntelligenceService.communicate(
            "reorder_products",
            context,
            "Explain why this order quantity was recommended.",
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
        context = {"anomaly": anomaly}
        provider, model, message = await IntelligenceService.communicate(
            "inventory_anomalies",
            context,
            "Explain why this inventory anomaly was flagged.",
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
        business_id: str, report: str, period: str, db: Session
    ) -> dict:
        days = {"daily": 1, "weekly": 7, "monthly": 30}[period]
        builders: dict[str, Callable] = {
            "sales": lambda: ReportService.get_sales_report(
                business_id, days, db
            ),
            "profit": lambda: ReportService.get_profit_report(
                business_id, days, db
            ),
            "inventory": lambda: ReportService.get_inventory_report(
                business_id, db
            ),
            "purchases": lambda: ReportService.get_purchase_report(
                business_id, days, db
            ),
        }
        context = {
            "report": report,
            "period": period,
            "analytics": builders[report](),
        }
        intent = "profitability" if report == "profit" else "sales_performance"
        provider, model, message = await IntelligenceService.communicate(
            intent,
            context,
            f"Summarize this {period} {report} report and list priorities.",
        )
        return {
            "intent": "report_summary",
            "provider": provider,
            "model": model,
            "message": message,
            "context": context,
        }
