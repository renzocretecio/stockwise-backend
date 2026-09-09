from types import SimpleNamespace

import pytest

from app.schemas.briefing import BriefingNarration
from app.services import briefing
from app.services.briefing import BriefingService
from app.services.entitlements import EntitlementService


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class GenerationDatabase:
    def __init__(self):
        self.results = [
            ScalarResult(
                SimpleNamespace(
                    id="business-id",
                    currency_code="PHP",
                    timezone="UTC",
                )
            ),
            ScalarResult(None),
        ]
        self.events = []

    def execute(self, _statement):
        return self.results.pop(0)

    def add(self, _record):
        return None

    def flush(self):
        return None

    def commit(self):
        self.events.append("commit")

    def refresh(self, _record):
        return None


class SuccessfulNarrator:
    provider = "groq"
    model = "test-model"

    async def generate(self, *_args):
        return narration()


class FailingNarrator(SuccessfulNarrator):
    async def generate(self, *_args):
        raise RuntimeError("Provider unavailable")


class TemplateNarrator:
    provider = "template"
    model = None

    async def generate(self, *_args):
        return narration()


def narration():
    return BriefingNarration(
        headline="Inventory briefing",
        summary=["First.", "Second.", "Third."],
    )


def prepare_generation(monkeypatch, narrator, events):
    monkeypatch.setattr(briefing.settings, "NARRATOR_PROVIDER", "groq")
    monkeypatch.setattr(briefing.settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(briefing, "GroqNarrator", narrator)
    monkeypatch.setattr(briefing, "TemplateNarrator", TemplateNarrator)
    monkeypatch.setattr(
        BriefingService,
        "_daily_business_recap",
        staticmethod(lambda *_args: None),
    )
    monkeypatch.setattr(
        BriefingService,
        "_collect_metrics",
        staticmethod(lambda *_args: []),
    )
    monkeypatch.setattr(
        BriefingService,
        "_recap_context",
        staticmethod(lambda *_args: {}),
    )
    monkeypatch.setattr(
        BriefingService,
        "_recommend",
        staticmethod(lambda *_args: []),
    )
    monkeypatch.setattr(
        briefing.DashboardService,
        "get_dashboard",
        staticmethod(lambda *_args: {}),
    )
    monkeypatch.setattr(
        BriefingService,
        "format",
        staticmethod(
            lambda record: {"provider": record.narrator_provider}
        ),
    )
    monkeypatch.setattr(
        EntitlementService,
        "consume_ai_insight",
        lambda *_args: events.append("reserve"),
    )
    monkeypatch.setattr(
        EntitlementService,
        "refund_ai_insight",
        lambda *_args: events.append("refund"),
    )


@pytest.mark.asyncio
async def test_manual_regeneration_consumes_one_ai_request(monkeypatch):
    events = []
    database = GenerationDatabase()
    prepare_generation(monkeypatch, SuccessfulNarrator, events)

    result = await BriefingService.generate(
        "business-id",
        "user-id",
        database,
        force=True,
    )

    assert result["provider"] == "groq"
    assert events == ["reserve"]


@pytest.mark.asyncio
async def test_failed_regeneration_refunds_ai_request(monkeypatch):
    events = []
    database = GenerationDatabase()
    prepare_generation(monkeypatch, FailingNarrator, events)

    result = await BriefingService.generate(
        "business-id",
        "user-id",
        database,
        force=True,
    )

    assert result["provider"] == "template"
    assert events == ["reserve", "refund"]


@pytest.mark.asyncio
async def test_automatic_daily_briefing_does_not_consume_quota(monkeypatch):
    events = []
    database = GenerationDatabase()
    prepare_generation(monkeypatch, SuccessfulNarrator, events)

    result = await BriefingService.generate(
        "business-id",
        "user-id",
        database,
        force=False,
    )

    assert result["provider"] == "groq"
    assert events == []
