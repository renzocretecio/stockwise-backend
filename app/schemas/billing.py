from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SubscriptionPlan = Literal["free", "pro", "business"]
SubscriptionStatus = Literal[
    "active",
    "trialing",
    "past_due",
    "cancelled",
    "expired",
]


class SubscriptionResponse(BaseModel):
    plan: SubscriptionPlan
    monthly_price_php: int
    additional_member_price_php: int | None
    additional_member_seats: int
    trial_eligible: bool
    status: str
    provider: str
    trial_ends_at: datetime | None = None
    current_period_ends_at: datetime | None = None
    cancel_at_period_end: bool
    limits: dict[str, int | None]
    features: dict[str, bool]
    usage: dict[str, int | str]


class SubscriptionAdminUpdate(BaseModel):
    plan: SubscriptionPlan
    status: SubscriptionStatus = "active"
    provider: str = Field(default="manual", max_length=32)
    trial_ends_at: datetime | None = None
    current_period_ends_at: datetime | None = None
    additional_member_seats: int | None = Field(default=None, ge=0, le=7)
