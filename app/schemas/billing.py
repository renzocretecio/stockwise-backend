from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SubscriptionPlan = Literal["free", "pro", "business"]
PaidSubscriptionPlan = Literal["pro", "business"]
BillingInterval = Literal["monthly", "yearly"]
SubscriptionStatus = Literal[
    "active",
    "trialing",
    "past_due",
    "cancelled",
    "expired",
]
UpgradeRequestStatus = Literal[
    "pending",
    "awaiting_payment",
    "payment_submitted",
    "approved",
    "rejected",
    "cancelled",
]


class SubscriptionResponse(BaseModel):
    plan: SubscriptionPlan
    monthly_price_php: int
    additional_member_price_php: int | None
    additional_member_seats: int
    trial_eligible: bool
    status: str
    provider: str
    billing_interval: BillingInterval
    trial_ends_at: datetime | None = None
    current_period_started_at: datetime | None = None
    current_period_ends_at: datetime | None = None
    cancel_at_period_end: bool
    limits: dict[str, int | None]
    features: dict[str, bool]
    usage: dict[str, int | str]


class BillingAdminAccessResponse(BaseModel):
    authorized: bool


class SubscriptionAdminUpdate(BaseModel):
    plan: SubscriptionPlan
    status: SubscriptionStatus = "active"
    provider: str = Field(default="manual", max_length=32)
    billing_interval: BillingInterval = "monthly"
    trial_ends_at: datetime | None = None
    current_period_started_at: datetime | None = None
    current_period_ends_at: datetime | None = None
    additional_member_seats: int | None = Field(default=None, ge=0, le=7)


class UpgradeRequestCreate(BaseModel):
    plan: PaidSubscriptionPlan
    billing_interval: BillingInterval = "monthly"
    additional_member_seats: int = Field(default=0, ge=0, le=7)


class UpgradeRequestApprove(BaseModel):
    plan: PaidSubscriptionPlan
    billing_interval: BillingInterval
    additional_member_seats: int = Field(default=0, ge=0, le=7)
    payment_reference: str | None = Field(default=None, max_length=255)
    admin_note: str | None = Field(default=None, max_length=500)


class UpgradeRequestAwaitingPayment(BaseModel):
    admin_note: str = Field(min_length=1, max_length=500)


class UpgradeRequestPaymentSubmission(BaseModel):
    payment_method: str = Field(min_length=1, max_length=64)
    payment_reference: str = Field(min_length=1, max_length=255)


class UpgradeRequestReject(BaseModel):
    admin_note: str = Field(min_length=1, max_length=500)


class UpgradeRequestResponse(BaseModel):
    id: str
    business_id: str
    business_name: str | None = None
    requested_by_name: str | None = None
    requested_by_email: str | None = None
    requested_plan: PaidSubscriptionPlan
    requested_billing_interval: BillingInterval
    requested_additional_member_seats: int
    quoted_amount_php: int
    status: UpgradeRequestStatus
    payment_method: str | None = None
    payment_reference: str | None = None
    payment_submitted_at: datetime | None = None
    admin_note: str | None = None
    approved_plan: PaidSubscriptionPlan | None = None
    approved_billing_interval: BillingInterval | None = None
    approved_additional_member_seats: int | None = None
    approved_amount_php: int | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class UpgradeRequestListResponse(BaseModel):
    items: list[UpgradeRequestResponse]
    total: int
    page: int
    page_size: int
    pages: int
    status_counts: dict[str, int]
