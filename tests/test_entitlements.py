from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.subscription import BusinessSubscription
from app.services.entitlements import (
    EntitlementService,
    PLAN_ENTITLEMENTS,
    PLAN_MONTHLY_PRICE_PHP,
    PRO_TRIAL_DAYS,
)


def test_effective_plan_defaults_to_free_without_subscription():
    assert EntitlementService.effective_plan(None) == "free"


def test_effective_plan_uses_free_for_inactive_subscription():
    subscription = BusinessSubscription(plan="pro", status="cancelled")

    assert EntitlementService.effective_plan(subscription) == "free"


def test_effective_plan_uses_active_subscription_plan():
    subscription = BusinessSubscription(plan="pro", status="active")

    assert EntitlementService.effective_plan(subscription) == "pro"


def test_effective_plan_uses_an_unexpired_pro_trial():
    subscription = BusinessSubscription(
        plan="pro",
        status="trialing",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert EntitlementService.effective_plan(subscription) == "pro"


def test_expired_pro_trial_falls_back_to_free():
    subscription = BusinessSubscription(
        plan="pro",
        status="trialing",
        trial_ends_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert EntitlementService.effective_plan(subscription) == "free"
    assert EntitlementService.effective_status(subscription) == "expired"


def test_free_plan_has_the_intended_limits_and_feature_gates():
    free = PLAN_ENTITLEMENTS["free"]

    assert free.active_sku_limit == 50
    assert free.member_limit == 1
    assert free.ai_insights_weekly == 5
    assert free.ai_insights is True
    assert free.offline_sync is False
    assert free.forecasting is True
    assert free.reorder_assistant is True
    assert free.weekly_owner_summary is False


def test_paid_plans_override_limits_without_removing_ai_capabilities():
    free = PLAN_ENTITLEMENTS["free"]
    pro = PLAN_ENTITLEMENTS["pro"]
    business = PLAN_ENTITLEMENTS["business"]

    assert pro.ai_insights_weekly == 30
    assert business.ai_insights_weekly == 150
    for capability in (
        "ai_insights",
        "forecasting",
        "reorder_assistant",
    ):
        assert getattr(free, capability) is True
        assert getattr(pro, capability) == getattr(free, capability)
        assert getattr(business, capability) == getattr(pro, capability)


def test_pro_additional_seats_raise_capacity_to_ten_members():
    pro = PLAN_ENTITLEMENTS["pro"]
    subscription = BusinessSubscription(
        plan="pro",
        status="active",
        additional_member_seats=7,
    )

    limit = EntitlementService.effective_member_limit(
        "pro",
        pro,
        subscription,
    )

    assert limit == 10


def test_start_pro_trial_records_one_time_trial(monkeypatch):
    subscription = BusinessSubscription(
        plan="free",
        status="active",
        trial_started_at=None,
    )
    user = SimpleNamespace(pro_trial_used_at=None)
    result = SimpleNamespace(scalar_one_or_none=lambda: user)
    database = SimpleNamespace(
        add=lambda _record: None,
        execute=lambda _statement: result,
        flush=lambda: None,
    )
    monkeypatch.setattr(
        EntitlementService,
        "subscription_for_business",
        lambda *_: subscription,
    )

    started = EntitlementService.start_pro_trial(
        "business-id",
        "user-id",
        database,
    )

    assert started.plan == "pro"
    assert started.status == "trialing"
    assert started.trial_started_at is not None
    assert started.trial_ends_at - started.trial_started_at == timedelta(
        days=PRO_TRIAL_DAYS,
    )

    with pytest.raises(HTTPException) as error:
        EntitlementService.start_pro_trial(
            "business-id",
            "user-id",
            database,
        )

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "user_trial_already_used"


def test_plan_prices_match_the_public_catalog():
    assert PLAN_MONTHLY_PRICE_PHP == {
        "free": 0,
        "pro": 299,
        "business": 899,
    }


def test_require_feature_returns_a_machine_readable_upgrade_error(monkeypatch):
    monkeypatch.setattr(
        EntitlementService,
        "entitlements_for_business",
        lambda *_: ("free", PLAN_ENTITLEMENTS["free"], None),
    )

    with pytest.raises(HTTPException) as error:
        EntitlementService.require_feature("business-id", "offline_sync", object())

    assert error.value.status_code == 402
    assert error.value.detail["code"] == "plan_feature_required"
    assert error.value.detail["feature"] == "offline_sync"
