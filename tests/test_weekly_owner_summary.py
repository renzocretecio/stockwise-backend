import json
from datetime import date

import pytest

from app.services import weekly_owner_summary
from app.services.communication import GroqCommunicationService
from app.services.weekly_owner_summary import WeeklyOwnerSummaryService


def test_weekly_period_is_seven_calendar_days(monkeypatch):
    class Business:
        timezone = "UTC"

    start, end = WeeklyOwnerSummaryService._period(
        Business(), date(2026, 9, 6)
    )

    assert start == date(2026, 8, 31)
    assert end == date(2026, 9, 6)


def test_email_contains_ai_and_deterministic_sections(monkeypatch):
    class Business:
        name = "Demo Shop"
        currency_code = "PHP"

    class Settings:
        included_sections = ["sales_performance", "inventory_health"]

    monkeypatch.setattr(weekly_owner_summary.settings, "APP_URL", "https://app.example")
    data = {
        "period": "2026-08-31 to 2026-09-06",
        "ai_executive_summary": "Sales improved during the period.",
        "kpis": {
            "sales": 186420,
            "gross_profit": 51300,
            "inventory_value": 100000,
            "low_stock_count": 5,
        },
        "needs_attention": [],
        "recommended_actions": [],
    }

    text, html = WeeklyOwnerSummaryService.render_email(Business(), data, Settings())

    assert "AI EXECUTIVE SUMMARY" in text
    assert "THIS WEEK AT A GLANCE" in text
    assert "PHP 186,420.00" in text
    assert "OPEN STOCKWISE" in text
    assert "Aug 31, 2026 to Sep 06, 2026" in text
    assert "Aug 31, 2026 to Sep 06, 2026" in html
    assert "https://app.example" in html


def test_email_renders_attention_explanations_as_readable_text(monkeypatch):
    class Business:
        name = "Demo Shop"
        currency_code = "PHP"

    class Settings:
        included_sections = ["reorder_recommendations"]

    data = {
        "period": "2026-08-31 to 2026-09-06",
        "ai_executive_summary": "Inventory needs review.",
        "kpis": {},
        "needs_attention": [
            {
                "product_name": "Wireless Earbuds",
                "explanation": [
                    "Method: Blended sales trend.",
                    "Lead-time demand is 19.24 units.",
                ],
            }
        ],
        "recommended_actions": [],
    }

    text, html = WeeklyOwnerSummaryService.render_email(Business(), data, Settings())

    assert "Wireless Earbuds: Method: Blended sales trend. Lead-time demand is 19.24 units." in text
    assert "['Method: Blended sales trend.'" not in text
    assert "['Method: Blended sales trend.'" not in html


@pytest.mark.asyncio
async def test_weekly_ai_receives_only_owner_summary_facts(monkeypatch):
    captured = {}

    async def fake_generate(self, instruction, context, schema):
        captured.update({"instruction": instruction, "context": context, "schema": schema})
        return json.dumps({"summary": "Sales were steady. Inventory needs review. Actions are listed. Owners can open Stockwise."})

    monkeypatch.setattr(GroqCommunicationService, "_generate", fake_generate)
    monkeypatch.setattr(weekly_owner_summary, "communication_enabled", lambda: True)
    data = {
        "period": "2026-08-31 to 2026-09-06",
        "sales": 186420,
        "sales_change_pct": 8.2,
        "gross_profit": 51300,
        "top_seller": "Wireless Earbuds",
        "low_stock_count": 5,
        "stockout_risk_count": 2,
        "dead_stock_value": 64500,
        "anomaly_count": 1,
        "priority_actions": [],
        "internal_only": "must not be sent",
    }

    result = await WeeklyOwnerSummaryService.add_ai_summary(data)

    assert result["ai_executive_summary"].startswith("Sales were steady")
    assert "internal_only" not in captured["context"]
    assert captured["context"]["period"] == "Aug 31, 2026 to Sep 06, 2026"
    assert "3-to-4 sentence" in captured["instruction"]