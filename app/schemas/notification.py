from datetime import date
from enum import IntEnum

from pydantic import BaseModel, EmailStr, Field, field_validator


DEFAULT_INCLUDED_SECTIONS = [
    "sales_performance",
    "inventory_health",
    "reorder_recommendations",
    "slow_moving_products",
    "inventory_anomalies",
    "supplier_issues",
]


class Weekday(IntEnum):
    monday = 0
    tuesday = 1
    wednesday = 2
    thursday = 3
    friday = 4
    saturday = 5
    sunday = 6


class WeeklyOwnerSummarySettingsPayload(BaseModel):
    enabled: bool = True
    send_weekday: Weekday = Weekday.monday
    send_hour: int = Field(default=7, ge=0, le=23)
    send_minute: int = Field(default=0, ge=0, le=59)
    recipients: list[EmailStr] = Field(min_length=1, max_length=10)
    included_sections: list[str] = Field(
        default_factory=lambda: DEFAULT_INCLUDED_SECTIONS.copy(),
        min_length=1,
        max_length=6,
    )
    action_required_only: bool = False

    @field_validator("recipients")
    @classmethod
    def normalize_recipients(cls, value: list[EmailStr]) -> list[str]:
        return list(dict.fromkeys(str(email).lower() for email in value))

    @field_validator("included_sections")
    @classmethod
    def validate_sections(cls, value: list[str]) -> list[str]:
        allowed = set(DEFAULT_INCLUDED_SECTIONS)
        if any(section not in allowed for section in value):
            raise ValueError("Unknown weekly summary section")
        return list(dict.fromkeys(value))


class WeeklyOwnerSummarySettingsResponse(WeeklyOwnerSummarySettingsPayload):
    business_id: str


class WeeklyOwnerSummaryResponse(BaseModel):
    period_start: date
    period_end: date
    ai_executive_summary: str
    kpis: dict
    needs_attention: list[dict]
    recommended_actions: list[dict]
    open_stockwise_url: str