from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.briefing import (
    BriefingService,
    ProductMetrics,
    TemplateNarrator,
)


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
