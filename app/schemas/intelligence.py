from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class IntelligenceMessage(BaseModel):
    answer: str = Field(max_length=1200)
    facts: list[str] = Field(default_factory=list, max_length=6)
    estimates: list[str] = Field(default_factory=list, max_length=4)
    recommended_actions: list[str] = Field(default_factory=list, max_length=4)
    limitations: list[str] = Field(default_factory=list, max_length=3)


class IntelligenceResponse(BaseModel):
    success: bool = True
    intent: str
    provider: Literal["groq", "template"]
    model: Optional[str] = None
    message: IntelligenceMessage
    context: dict[str, Any]


class AskIntelligenceRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class ReportSummaryRequest(BaseModel):
    report: Literal["sales", "profit", "inventory", "purchases"]
    period: Literal["daily", "weekly", "monthly"] = "monthly"
