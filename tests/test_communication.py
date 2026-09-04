import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.services import communication
from app.services.communication import (
    GroqCommunicationService,
    format_ai_context,
)


def test_format_ai_context_humanizes_nested_temporal_values():
    zone = timezone(timedelta(hours=8))
    context = {
        "as_of": date(2026, 9, 1),
        "anomaly": {
            "occurred_at": datetime(2026, 9, 1, 14, 5, tzinfo=zone),
            "resolved_at": "2026-09-02T08:30:00Z",
        },
        "series": [{"date": "2026-09-03", "quantity": 5}],
        "cutoff_time": time(17, 30, tzinfo=timezone.utc),
    }

    result = format_ai_context(context)

    assert result["as_of"] == "Sep 01, 2026"
    assert result["anomaly"]["occurred_at"] == ("Sep 01, 2026 at 02:05 PM (UTC+08:00)")
    assert result["anomaly"]["resolved_at"] == ("Sep 02, 2026 at 08:30 AM (UTC)")
    assert result["series"][0]["date"] == "Sep 03, 2026"
    assert result["cutoff_time"] == "05:30:00 PM (UTC)"
    assert context["anomaly"]["occurred_at"].isoformat() == (
        "2026-09-01T14:05:00+08:00"
    )


def test_format_ai_context_rounds_numbers_and_omits_missing_values():
    context = {
        "daily_demand": 4.5403174603174605,
        "stock_value": Decimal("18.2366"),
        "whole_quantity": Decimal("3.000"),
        "integer_count": 7,
        "is_estimate": True,
        "negative_tie": -1.235,
        "negative_zero": -0.001,
        "missing": None,
        "nested": {
            "percentage": 12.3456,
            "unavailable": None,
        },
        "values": [None, 1.239, {"amount": Decimal("2.345")}],
        "invalid_numbers": {
            "not_a_number": float("nan"),
            "infinity": Decimal("Infinity"),
        },
    }

    result = format_ai_context(context)

    assert result["daily_demand"] == 4.54
    assert result["stock_value"] == 18.24
    assert result["whole_quantity"] == 3
    assert result["integer_count"] == 7
    assert isinstance(result["integer_count"], int)
    assert result["is_estimate"] is True
    assert result["negative_tie"] == -1.24
    assert result["negative_zero"] == 0
    assert "missing" not in result
    assert result["nested"] == {"percentage": 12.35}
    assert result["values"] == [1.24, {"amount": 2.35}]
    assert result["invalid_numbers"] == {}
    assert "null" not in json.dumps(result, allow_nan=False)
    assert context["daily_demand"] == 4.5403174603174605
    assert context["missing"] is None


@pytest.mark.asyncio
async def test_groq_payload_receives_only_formatted_context(monkeypatch):
    captured = {}

    class FakeResponse:
        is_success = True
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [
                    {
                        "message": {"content": "{}"}
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(communication.httpx, "AsyncClient", FakeClient)
    await GroqCommunicationService()._generate(
        "Explain",
        {
            "occurred_at": "2026-09-01T06:15:00+00:00",
            "order_by_date": date(2026, 9, 2),
            "daily_demand": 4.5403174603174605,
            "estimated_stockout_date": None,
        },
        {"type": "object"},
    )

    prompt = captured["json"]["messages"][1]["content"]
    context = json.loads(prompt)["intelligence_context"]
    assert context["occurred_at"] == "Sep 01, 2026 at 06:15 AM (UTC)"
    assert context["order_by_date"] == "Sep 02, 2026"
    assert context["daily_demand"] == 4.54
    assert "estimated_stockout_date" not in context
    assert "null" not in prompt
    assert captured["json"]["model"] == "openai/gpt-oss-20b"
    assert captured["json"]["reasoning_effort"] == "low"
    response_format = captured["json"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert captured["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_groq_explanation_clamps_lists_after_generation(monkeypatch):
    service = GroqCommunicationService()
    response = {
        "answer": "Review the recommendation.",
        "facts": [f"Fact {index}" for index in range(8)],
        "estimates": [f"Estimate {index}" for index in range(6)],
        "recommended_actions": [f"Action {index}" for index in range(6)],
        "limitations": [f"Limitation {index}" for index in range(5)],
    }

    async def fake_generate(instruction, context, schema):
        assert "maxItems" not in json.dumps(schema)
        return json.dumps(response)

    monkeypatch.setattr(service, "_generate", fake_generate)

    message = await service.explain("Explain", {"forecast": {}})

    assert len(message.facts) == 6
    assert len(message.estimates) == 4
    assert len(message.recommended_actions) == 4
    assert len(message.limitations) == 3


@pytest.mark.asyncio
async def test_groq_explanation_requires_business_currency(monkeypatch):
    service = GroqCommunicationService()

    async def fake_generate(instruction, context, schema):
        assert "Use business.currency_code" in instruction
        assert "Never default to USD" in instruction
        assert context["business"]["currency_code"] == "PHP"
        return json.dumps(
            {
                "answer": "Revenue was ₱6,982.",
                "facts": [],
                "estimates": [],
                "recommended_actions": [],
                "limitations": [],
            }
        )

    monkeypatch.setattr(service, "_generate", fake_generate)

    message = await service.explain(
        "Explain revenue",
        {
            "business": {"currency_code": "PHP"},
            "total_revenue": 6982,
        },
    )

    assert message.answer == "Revenue was ₱6,982."


@pytest.mark.asyncio
async def test_groq_briefing_requires_business_currency(monkeypatch):
    service = GroqCommunicationService()

    async def fake_generate(instruction, context, schema):
        assert "business.currency_code" in instruction
        assert "business.currency_symbol" in instruction
        assert "Never default to USD" in instruction
        assert context["business"] == {
            "currency_code": "PHP",
            "currency_symbol": "₱",
        }
        return json.dumps(
            {
                "headline": "Review ₱6,982 in sales",
                "summary": ["One", "Two", "Three"],
            }
        )

    monkeypatch.setattr(service, "_generate", fake_generate)

    narration = await service.create_briefing(
        {
            "business": {
                "currency_code": "PHP",
                "currency_symbol": "₱",
            },
            "business_metrics": {"sales_today": 6982},
        }
    )

    assert "₱6,982" in narration.headline


@pytest.mark.asyncio
async def test_groq_briefing_clamps_oversized_summary(monkeypatch):
    service = GroqCommunicationService()
    response = {
        "headline": "Review inventory",
        "summary": [f"Item {index}" for index in range(6)],
    }

    async def fake_generate(instruction, context, schema):
        assert "exactly three string items" in instruction
        assert "never more than three" in instruction
        assert "maxItems" not in json.dumps(schema)
        return json.dumps(response)

    monkeypatch.setattr(service, "_generate", fake_generate)

    narration = await service.create_briefing({})

    assert narration.summary == ["Item 0", "Item 1", "Item 2"]
