import pytest
from fastapi import HTTPException

from app.services.intelligence import IntelligenceService


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What should I reorder this week?", "reorder_products"),
        ("Which products are not selling?", "slow_moving_products"),
        ("Did we have unusual stock losses?", "inventory_anomalies"),
        ("What were my top selling products?", "top_selling_products"),
        ("Why were sales lower this week?", "sales_performance"),
        ("Which products have the best profit?", "profitability"),
        ("Which supplier has the longest lead time?", "supplier_performance"),
    ],
)
def test_questions_are_routed_to_approved_intents(question, intent):
    assert IntelligenceService.classify(question) == intent


def test_unsupported_question_is_rejected_before_gemini():
    with pytest.raises(HTTPException) as error:
        IntelligenceService.classify("Write me a poem")
    assert error.value.status_code == 422


def test_reorder_fallback_uses_precalculated_quantity():
    message = IntelligenceService.fallback(
        "reorder_products",
        {
            "forecasts": [
                {
                    "product_name": "Wireless Earbuds",
                    "recommended_order_quantity": 78,
                }
            ]
        },
    )
    assert "78 units" in message.answer
    assert "Wireless Earbuds" in message.answer
