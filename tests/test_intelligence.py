import pytest
from types import SimpleNamespace

from app.services import intelligence
from app.services.entitlements import EntitlementService
from app.services.intelligence import IntelligenceService


@pytest.mark.asyncio
async def test_template_response_does_not_consume_ai_quota(monkeypatch):
    def unexpected_consume(*_args, **_kwargs):
        raise AssertionError("Template responses must not consume quota")

    monkeypatch.setattr(intelligence, "communication_enabled", lambda: False)
    monkeypatch.setattr(
        EntitlementService,
        "consume_ai_insight",
        unexpected_consume,
    )

    provider, _, _ = await IntelligenceService.communicate(
        "reorder_products",
        {"forecasts": []},
        "Explain the recommendation.",
        "business-id",
        object(),
    )

    assert provider == "template"


@pytest.mark.asyncio
async def test_failed_provider_request_is_refunded_on_failure(monkeypatch):
    events = []
    database = SimpleNamespace(
        commit=lambda: events.append("commit"),
        rollback=lambda: events.append("rollback"),
    )

    class FailingCommunicator:
        model = "test-model"

        async def explain(self, *_args, **_kwargs):
            raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(intelligence, "communication_enabled", lambda: True)
    monkeypatch.setattr(
        intelligence,
        "GroqCommunicationService",
        FailingCommunicator,
    )
    monkeypatch.setattr(
        EntitlementService,
        "consume_ai_insight",
        lambda *_args, **_kwargs: events.append("reserve"),
    )
    monkeypatch.setattr(
        EntitlementService,
        "refund_ai_insight",
        lambda *_args, **_kwargs: events.append("refund"),
    )

    provider, _, _ = await IntelligenceService.communicate(
        "reorder_products",
        {"forecasts": []},
        "Explain the recommendation.",
        "business-id",
        database,
    )

    assert provider == "template"
    assert events == ["reserve", "commit", "refund", "commit"]


@pytest.mark.asyncio
async def test_successful_provider_request_consumes_quota_once(monkeypatch):
    events = []
    database = SimpleNamespace(commit=lambda: events.append("commit"))

    class SuccessfulCommunicator:
        model = "test-model"

        async def explain(self, *_args, **_kwargs):
            return IntelligenceService.fallback(
                "reorder_products",
                {"forecasts": []},
            )

    monkeypatch.setattr(intelligence, "communication_enabled", lambda: True)
    monkeypatch.setattr(
        intelligence,
        "GroqCommunicationService",
        SuccessfulCommunicator,
    )
    monkeypatch.setattr(
        EntitlementService,
        "consume_ai_insight",
        lambda *_args, **_kwargs: events.append("reserve"),
    )
    monkeypatch.setattr(
        EntitlementService,
        "refund_ai_insight",
        lambda *_args, **_kwargs: events.append("refund"),
    )

    provider, model, _ = await IntelligenceService.communicate(
        "reorder_products",
        {"forecasts": []},
        "Explain the recommendation.",
        "business-id",
        database,
    )

    assert provider == "groq"
    assert model == "test-model"
    assert events == ["reserve", "commit"]


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


def test_business_currency_is_added_to_intelligence_context():
    business = SimpleNamespace(
        currency_code="PHP",
        timezone="Asia/Manila",
    )
    result = SimpleNamespace(
        scalar_one_or_none=lambda: business,
    )
    database = SimpleNamespace(execute=lambda statement: result)

    context = IntelligenceService.with_business_context(
        "business-id",
        {"total_revenue": 6982},
        database,
    )

    assert context == {
        "total_revenue": 6982,
        "business": {
            "currency_code": "PHP",
            "timezone": "Asia/Manila",
        },
    }
