from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class BriefingNarration(BaseModel):
    headline: str = Field(max_length=200)
    summary: list[str] = Field(min_length=3, max_length=3)


class RecommendationResponse(BaseModel):
    id: str
    product_id: Optional[str] = None
    purchase_id: Optional[str] = None
    type: str
    priority: str
    priority_score: int
    confidence: str
    title: str
    recommended_action: str
    evidence: list[str]
    metrics: dict[str, Any]
    rule_id: str
    dismissed_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class BriefingResponse(BaseModel):
    id: str
    briefing_date: date
    status: str
    headline: str
    summary: list[str]
    narrator_provider: str
    narrator_model: Optional[str] = None
    generated_at: datetime
    recommendations: list[RecommendationResponse]


class BriefingEnvelope(BaseModel):
    success: bool = True
    briefing: Optional[BriefingResponse] = None


class RecommendationActionResponse(BaseModel):
    success: bool = True
    recommendation_id: str
    status: str
