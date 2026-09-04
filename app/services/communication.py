import json
import math
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any
from uuid import UUID

import httpx

from app.config.settings import settings
from app.schemas.briefing import BriefingNarration
from app.schemas.intelligence import IntelligenceMessage


TEMPORAL_KEYS = {
    "as_of",
    "date",
    "time",
    "timestamp",
}
AI_NUMBER_QUANTUM = Decimal("0.01")


def _is_temporal_key(key: str | None) -> bool:
    if not key:
        return False
    normalized = key.casefold()
    return normalized in TEMPORAL_KEYS or normalized.endswith(
        ("_at", "_date", "_time", "_timestamp")
    )


def _timezone_label(value: datetime | time) -> str:
    if value.tzinfo is None:
        return "timezone unspecified"
    name = value.tzname()
    return name or "timezone unspecified"


def _format_datetime(value: datetime) -> str:
    rendered = value.strftime("%b %d, %Y at %I:%M %p")
    return f"{rendered} ({_timezone_label(value)})"


def _format_date(value: date) -> str:
    return value.strftime("%b %d, %Y")


def _format_time(value: time) -> str:
    rendered = value.strftime("%I:%M:%S %p")
    return f"{rendered} ({_timezone_label(value)})"


def _format_temporal_string(value: str, key: str | None) -> str:
    normalized = value.strip()
    try:
        key_name = key.casefold() if key else ""
        if key_name.endswith("_time") or key_name == "time":
            return _format_time(time.fromisoformat(normalized))
        if "T" in normalized or " " in normalized:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            return _format_datetime(parsed)
        return _format_date(date.fromisoformat(normalized))
    except ValueError:
        return value


def _format_number(value: Decimal | float) -> int | float | None:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal_value.is_finite():
        return None
    try:
        rounded = decimal_value.quantize(
            AI_NUMBER_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation:
        return None
    if rounded == 0:
        return 0
    if rounded == rounded.to_integral_value():
        return int(rounded)
    return float(rounded)


def format_ai_context(value: Any, key: str | None = None) -> Any:
    """Return a concise AI-facing copy without missing values."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return _format_datetime(value)
    if isinstance(value, date):
        return _format_date(value)
    if isinstance(value, time):
        return _format_time(value)
    if isinstance(value, str) and _is_temporal_key(key):
        return _format_temporal_string(value, key)
    if isinstance(value, (Decimal, float)):
        return _format_number(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return format_ai_context(value.value, key)
    if isinstance(value, dict):
        formatted = {}
        for item_key, item_value in value.items():
            formatted_value = format_ai_context(
                item_value,
                str(item_key),
            )
            if formatted_value is not None:
                formatted[item_key] = formatted_value
        return formatted
    if isinstance(value, (list, tuple, set)):
        formatted = [format_ai_context(item, key) for item in value]
        return [item for item in formatted if item is not None]
    return value


class GroqCommunicationService:
    """Communicates backend intelligence without calculating business facts."""

    provider = "groq"

    def __init__(self):
        self.model = settings.GROQ_MODEL

    async def _generate(self, instruction: str, context: dict, schema: dict):
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": instruction,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "intelligence_context": format_ai_context(context)
                        },
                        allow_nan=False,
                    ),
                }
            ],
            "max_completion_tokens": 1200,
            "reasoning_effort": "low",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "stockwise_response",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        async with httpx.AsyncClient(
            timeout=settings.NARRATOR_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if not response.is_success:
            message = ""
            try:
                message = response.json().get("error", {}).get("message", "")
            except (TypeError, ValueError):
                pass
            suffix = f": {message[:500]}" if message else ""
            raise RuntimeError(
                f"Groq API request failed with status "
                f"{response.status_code}{suffix}"
            )
        data = response.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not text:
            raise RuntimeError("Groq API returned no final text response")
        return text

    async def create_briefing(self, context: dict) -> BriefingNarration:
        instruction = (
            "Use only the supplied facts. Do not recalculate or invent any "
            "number, date, cause, or recommendation. Return a JSON object "
            "with a short headline and a summary array containing exactly "
            "three string items, never more than three. Each item should be "
            "one sentence; do not split one item into multiple array items. "
            "The UI combines those three items into one short recap, so make "
            "them a cohesive two-to-four sentence narrative with no headings, "
            "labels, or action commands. "
            "When daily_recap is present, cover what happened on report_date, "
            "then the relevant recorded driver, return, receipt, or adjustment, "
            "then the most urgent approved inventory risk. Clearly qualify "
            "estimates and low confidence. "
            "Use business.currency_code and business.currency_symbol for "
            "every monetary value. Never default to USD or use $ unless "
            "the business currency code is USD."
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "headline": {"type": "string"},
                "summary": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                },
            },
            "required": ["headline", "summary"],
        }
        text = await self._generate(instruction, context, schema)
        data = json.loads(text)
        data["summary"] = data["summary"][:3]
        return BriefingNarration.model_validate(data)

    async def create_weekly_owner_summary(self, facts: dict) -> str:
        instruction = (
            "Turn the supplied weekly owner summary facts into a 3-to-4 "
            "sentence executive summary. Use only the supplied facts. Do not "
            "calculate, alter, round, reinterpret, or introduce any number, "
            "date, cause, product, or recommendation. Mention the period and "
            "the most important sales and inventory facts, and keep the tone "
            "clear and useful to a business owner. Return plain text only, "
            "with no heading, bullets, markdown, or labels."
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        text = await self._generate(instruction, facts, schema)
        return json.loads(text)["summary"]

    async def explain(self, task: str, context: dict) -> IntelligenceMessage:
        instruction = (
            f"Task: {task}. Explain only the supplied intelligence context. "
            "Never calculate new values, infer missing causes, or introduce "
            "facts not present in the context. Use business.currency_code "
            "for every monetary value and use its appropriate symbol. Never "
            "default to USD or use $ unless the currency code is USD. "
            "Separate recorded facts, "
            "estimates, approved recommendations, and limitations. Keep the "
            "answer concise and useful to a small-business owner. Return no "
            "more than 6 facts, 4 estimates, 4 recommended actions, and 3 "
            "limitations."
        )
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "answer": {"type": "string"},
                "facts": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "estimates": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "limitations": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "answer",
                "facts",
                "estimates",
                "recommended_actions",
                "limitations",
            ],
        }
        text = await self._generate(instruction, context, schema)
        data = json.loads(text)
        for field, limit in {
            "facts": 6,
            "estimates": 4,
            "recommended_actions": 4,
            "limitations": 3,
        }.items():
            data[field] = data[field][:limit]
        return IntelligenceMessage.model_validate(data)


def communication_enabled() -> bool:
    return bool(settings.NARRATOR_PROVIDER == "groq" and settings.GROQ_API_KEY)
