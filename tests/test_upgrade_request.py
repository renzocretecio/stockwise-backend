from datetime import datetime, timezone

from app.models.subscription import BusinessSubscription
from app.services.entitlements import EntitlementService
from app.services.upgrade_request import UpgradeRequestService


def test_upgrade_quotes_use_the_selected_billing_period():
    assert UpgradeRequestService.quote_amount("pro", "monthly", 0) == 299
    assert UpgradeRequestService.quote_amount("pro", "yearly", 2) == 5_484
    assert UpgradeRequestService.quote_amount("business", "yearly", 0) == 10_788


def test_yearly_period_end_preserves_the_calendar_date():
    start = datetime(2026, 9, 10, 8, 30, tzinfo=timezone.utc)

    assert UpgradeRequestService._period_end(start, "monthly") == datetime(
        2026,
        10,
        10,
        8,
        30,
        tzinfo=timezone.utc,
    )
    assert UpgradeRequestService._period_end(start, "yearly") == datetime(
        2027,
        9,
        10,
        8,
        30,
        tzinfo=timezone.utc,
    )


def test_expired_active_subscription_falls_back_to_free():
    subscription = BusinessSubscription(
        plan="pro",
        status="active",
        current_period_ends_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    assert EntitlementService.effective_plan(subscription) == "free"
    assert EntitlementService.effective_status(subscription) == "expired"
