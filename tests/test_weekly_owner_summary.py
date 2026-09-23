import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.services import weekly_owner_summary
from app.services.communication import GroqCommunicationService
from app.services.weekly_owner_summary import WeeklyOwnerSummaryService


def test_weekly_period_is_seven_calendar_days(monkeypatch):
    class Business:
        timezone = "UTC"

    start, end = WeeklyOwnerSummaryService._period(Business(), date(2026, 9, 6))

    assert start == date(2026, 8, 31)
    assert end == date(2026, 9, 6)


def test_due_period_uses_business_timezone_and_allows_late_run():
    business = SimpleNamespace(timezone="Asia/Manila")
    settings = SimpleNamespace(
        send_weekday=6,
        send_hour=12,
        send_minute=0,
        last_sent_period_end=None,
        next_attempt_at=None,
    )
    now = datetime(2026, 9, 20, 4, 4, tzinfo=timezone.utc)

    period_end = WeeklyOwnerSummaryService._due_period_end(
        business,
        settings,
        now,
    )

    assert period_end == date(2026, 9, 19)


def test_due_period_waits_until_scheduled_local_time():
    business = SimpleNamespace(timezone="Asia/Manila")
    settings = SimpleNamespace(
        send_weekday=6,
        send_hour=12,
        send_minute=0,
        last_sent_period_end=None,
        next_attempt_at=None,
    )
    now = datetime(2026, 9, 20, 3, 59, tzinfo=timezone.utc)

    assert (
        WeeklyOwnerSummaryService._due_period_end(
            business,
            settings,
            now,
        )
        is None
    )


def test_due_period_catches_up_after_scheduled_weekday():
    business = SimpleNamespace(timezone="Asia/Manila")
    settings = SimpleNamespace(
        send_weekday=6,
        send_hour=12,
        send_minute=0,
        last_sent_period_end=None,
        next_attempt_at=None,
    )
    now = datetime(2026, 9, 21, 1, 0, tzinfo=timezone.utc)

    period_end = WeeklyOwnerSummaryService._due_period_end(
        business,
        settings,
        now,
    )

    assert period_end == date(2026, 9, 19)


def test_due_period_respects_retry_backoff():
    now = datetime(2026, 9, 20, 4, 4, tzinfo=timezone.utc)
    business = SimpleNamespace(timezone="Asia/Manila")
    settings = SimpleNamespace(
        send_weekday=6,
        send_hour=12,
        send_minute=0,
        last_sent_period_end=None,
        next_attempt_at=now + timedelta(minutes=5),
    )

    assert (
        WeeklyOwnerSummaryService._due_period_end(
            business,
            settings,
            now,
        )
        is None
    )


def test_email_contains_ai_and_deterministic_sections(monkeypatch):
    class Business:
        name = "Demo Shop"
        currency_code = "PHP"

    class Settings:
        included_sections = ["sales_performance", "inventory_health"]

    monkeypatch.setattr(
        weekly_owner_summary.settings, "APP_URL", "https://app.example"
    )
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

    text, html = WeeklyOwnerSummaryService.render_email(
        Business(), data, Settings()
    )

    assert "AI EXECUTIVE SUMMARY" in text
    assert "THIS WEEK AT A GLANCE" in text
    assert "PHP 186,420.00" in text
    assert "OPEN KITASTOCK" in text
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

    text, html = WeeklyOwnerSummaryService.render_email(
        Business(), data, Settings()
    )

    assert (
        "Wireless Earbuds: Method: Blended sales trend. Lead-time demand is 19.24 units."
        in text
    )
    assert "['Method: Blended sales trend.'" not in text
    assert "['Method: Blended sales trend.'" not in html


@pytest.mark.asyncio
async def test_weekly_ai_receives_only_owner_summary_facts(monkeypatch):
    captured = {}

    async def fake_generate(self, instruction, context, schema):
        captured.update(
            {"instruction": instruction, "context": context, "schema": schema}
        )
        return json.dumps(
            {
                "summary": "Sales were steady. Inventory needs review. Actions are listed. Owners can open KitaStock."
            }
        )

    monkeypatch.setattr(GroqCommunicationService, "_generate", fake_generate)
    monkeypatch.setattr(
        weekly_owner_summary, "communication_enabled", lambda: True
    )
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


@pytest.mark.asyncio
async def test_scheduled_delivery_isolates_business_failures(monkeypatch):
    now = datetime(2026, 9, 20, 4, 4, tzinfo=timezone.utc)
    period_end = date(2026, 9, 19)
    first_business = SimpleNamespace(id="first", name="First")
    second_business = SimpleNamespace(id="second", name="Second")

    def summary_settings(identifier):
        return SimpleNamespace(
            id=identifier,
            recipients=[f"{identifier}@example.com"],
            included_sections=[],
            last_attempt_period_end=None,
            last_attempted_at=None,
            last_sent_period_end=None,
            last_sent_at=None,
            last_delivery_status=None,
            last_delivery_error=None,
            consecutive_failures=0,
            next_attempt_at=None,
        )

    first_settings = summary_settings("first-settings")
    second_settings = summary_settings("second-settings")

    class FakeDb:
        def __init__(self):
            self.rows = {
                first_settings.id: first_settings,
                second_settings.id: second_settings,
            }

        def add(self, row):
            self.rows[row.id] = row

        def commit(self):
            return None

        def rollback(self):
            return None

        def get(self, model, identifier):
            return self.rows.get(identifier)

    db = FakeDb()
    monkeypatch.setattr(
        WeeklyOwnerSummaryService,
        "due_businesses",
        lambda current, session: [
            (first_business, first_settings, period_end),
            (second_business, second_settings, period_end),
        ],
    )
    monkeypatch.setattr(
        weekly_owner_summary.EntitlementService,
        "entitlements_for_business",
        lambda business_id, session: (
            "pro",
            SimpleNamespace(weekly_owner_summary=True),
            None,
        ),
    )
    monkeypatch.setattr(
        WeeklyOwnerSummaryService,
        "build_data",
        lambda business, session, end: {"period_end": end},
    )

    async def add_summary(data):
        return data

    monkeypatch.setattr(
        WeeklyOwnerSummaryService,
        "add_ai_summary",
        add_summary,
    )
    monkeypatch.setattr(
        WeeklyOwnerSummaryService,
        "render_email",
        lambda business, data, row: ("text", "html"),
    )

    def send_email(recipients, subject, text, html):
        if "First" in subject:
            raise RuntimeError("Temporary SMTP error")

    monkeypatch.setattr(
        WeeklyOwnerSummaryService,
        "send_email",
        send_email,
    )

    result = await WeeklyOwnerSummaryService.send_due(now, db)

    assert result.due == 2
    assert result.failed == 1
    assert result.sent == 1
    assert first_settings.last_delivery_status == "failed"
    assert first_settings.consecutive_failures == 1
    assert first_settings.next_attempt_at == now + timedelta(minutes=5)
    assert second_settings.last_delivery_status == "sent"
    assert second_settings.last_sent_period_end == period_end.isoformat()
