import json
from typing import Any

import httpx

from app.config.settings import settings
from app.schemas.briefing import BriefingNarration
from app.schemas.intelligence import IntelligenceMessage


class GeminiCommunicationService:
    """Communicates backend intelligence without calculating business facts."""

    provider = "gemini"

    def __init__(self):
        self.model = settings.GEMINI_MODEL

    async def _generate(self, instruction: str, context: dict, schema: dict):
        api_root = "https://generativelanguage.googleapis.com/v1beta/models"
        url = f"{api_root}/{self.model}:generateContent"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "instruction": instruction,
                                    "intelligence_context": context,
                                },
                                default=str,
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 1200,
                "thinkingConfig": {"thinkingLevel": "minimal"},
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        async with httpx.AsyncClient(
            timeout=settings.NARRATOR_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(
                url,
                headers={"x-goog-api-key": settings.GEMINI_API_KEY},
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
                f"Gemini API request failed with status "
                f"{response.status_code}{suffix}"
            )
        data = response.json()
        parts = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
        )
        text = next(
            (
                part["text"]
                for part in parts
                if part.get("text") and not part.get("thought")
            ),
            None,
        )
        if not text:
            raise RuntimeError("Gemini API returned no final text response")
        return text

    async def create_briefing(self, context: dict) -> BriefingNarration:
        instruction = (
            "Use only the supplied facts. Do not recalculate or invent any "
            "number, date, cause, or recommendation. Write a short headline "
            "and exactly three summary items. Put the most urgent approved "
            "action first. Clearly qualify estimates and low confidence."
        )
        schema = {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "summary": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 3,
                },
            },
            "required": ["headline", "summary"],
        }
        text = await self._generate(instruction, context, schema)
        return BriefingNarration.model_validate_json(text)

    async def explain(self, task: str, context: dict) -> IntelligenceMessage:
        instruction = (
            f"Task: {task}. Explain only the supplied intelligence context. "
            "Never calculate new values, infer missing causes, or introduce "
            "facts not present in the context. Separate recorded facts, "
            "estimates, approved recommendations, and limitations. Keep the "
            "answer concise and useful to a small-business owner."
        )
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "facts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 6,
                },
                "estimates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                },
                "recommended_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 4,
                },
                "limitations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 3,
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
        return IntelligenceMessage.model_validate_json(text)


def communication_enabled() -> bool:
    return bool(
        settings.NARRATOR_PROVIDER == "gemini" and settings.GEMINI_API_KEY
    )
