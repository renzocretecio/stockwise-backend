from datetime import date
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


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


class ReportSummaryRequest(BaseModel):
    report: Literal[
        "sales",
        "purchases",
        "inventory",
        "profit",
        "low_stock",
        "movements",
    ]
    days: Literal[7, 30, 90, 365] = 30
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self):
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("Both start_date and end_date are required.")
        if self.start_date is None or self.end_date is None:
            return self
        if self.start_date > self.end_date:
            raise ValueError(
                "start_date must be on or before end_date."
            )
        if (self.end_date - self.start_date).days + 1 > 365:
            raise ValueError("The date range cannot exceed 365 days.")
        return self
