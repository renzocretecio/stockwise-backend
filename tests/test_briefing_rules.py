from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.briefing import (
    BriefingService,
    DailyBusinessRecap,
    ProductMetrics,
    TemplateNarrator,
)
from app.schemas.briefing import BriefingNarration


def metric(**overrides):
    values = dict(
        product_id="p1",
        product_name="Widget",
        current_stock=Decimal("5"),
        reorder_point=Decimal("10"),
        safety_stock=Decimal("2"),
        average_cost=Decimal("4"),
        average_daily_sales_7d=Decimal("1"),
        average_daily_sales_30d=Decimal("1"),
        sales_yesterday=Decimal("1"),
        sales_change_percent=None,
        incoming_stock=Decimal("0"),
        lead_time_days=7,
        days_since_last_sale=0,
        latest_count_variance=None,
    )
    values.update(overrides)
    return ProductMetrics(**values)


class EmptyDb:
    class Result:
        def scalars(self):
            return self

        def all(self):
            return []

    def execute(self, _):
        return self.Result()


def test_stockout_rule_has_highest_priority():
    result = BriefingService._recommend(
        [metric()],
        type("B", (), {"id": "b", "timezone": "UTC"})(),
        __import__("datetime").date.today(),
        EmptyDb(),
    )
    assert result[0]["type"] == "stockout_risk"
    assert result[0]["priority"] == "high"


def test_dead_stock_rule_requires_stock_on_hand():
    result = BriefingService._recommend(
        [
            metric(
                current_stock=Decimal("4"),
                average_daily_sales_7d=Decimal("0"),
                average_daily_sales_30d=Decimal("0"),
                days_since_last_sale=100,
            )
        ],
        type("B", (), {"id": "b", "timezone": "UTC"})(),
        __import__("datetime").date.today(),
        EmptyDb(),
    )
    assert any(item["type"] == "dead_stock" for item in result)


def test_sales_change_rule_uses_precalculated_percentage():
    result = BriefingService._recommend(
        [metric(sales_change_percent=Decimal("40"))],
        SimpleNamespace(id="b", timezone="UTC"),
        __import__("datetime").date.today(),
        EmptyDb(),
    )
    assert any(item["type"] == "sales_change" for item in result)


@pytest.mark.asyncio
async def test_template_narrator_always_returns_three_sentences():
    narration = await TemplateNarrator().generate([])
    assert len(narration.summary) == 3


@pytest.mark.asyncio
async def test_template_narrator_leads_with_daily_business_recap():
    recap = DailyBusinessRecap(
        date=date(2026, 9, 2),
        gross_sales=Decimal("1000"),
        net_sales=Decimal("900"),
        gross_profit=Decimal("400"),
        sales_count=4,
        items_sold=Decimal("8"),
        return_count=1,
        refund_amount=Decimal("100"),
        received_purchase_count=0,
        received_purchase_value=Decimal("0"),
        adjustment_count=0,
        adjustment_quantity=Decimal("0"),
        sales_change_percent=Decimal("12.5"),
        top_product_name="Wireless Earbuds",
        top_product_quantity=Decimal("5"),
    )

    narration = await TemplateNarrator().generate(
        [{"recommended_action": "Review replenishment needs"}],
        recap,
        "₱",
    )

    assert narration.headline == "Sep 02: ₱900.00 in net sales"
    assert "up 12.5%" in narration.summary[0]
    assert "Wireless Earbuds" in narration.summary[1]
    assert "inventory item(s) need attention" in narration.summary[2]


def test_narration_uses_business_currency_symbol():
    narration = BriefingService._localize_narration(
        BriefingNarration(
            headline="Revenue is $6,982",
            summary=[
                "Inventory is worth $10,000.",
                "Gross profit is $4,000.",
                "Review the $500 purchase first.",
            ],
        ),
        "PHP",
    )

    assert narration.headline == "Revenue is ₱6,982"
    assert all("$" not in line for line in narration.summary)
