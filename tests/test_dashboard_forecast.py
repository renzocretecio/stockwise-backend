from decimal import Decimal

from app.services.dashboard import (
    calculate_reorder,
    count_variance_threshold,
)


def test_reorder_uses_weighted_velocity_and_subtracts_incoming_stock():
    result = calculate_reorder(
        average_7d=Decimal("5"),
        average_30d=Decimal("3"),
        current_stock=Decimal("12"),
        incoming_stock=Decimal("8"),
        safety_stock=Decimal("10"),
        lead_time_days=7,
    )
    assert result.daily_demand == Decimal("4.4")
    assert result.lead_time_demand == Decimal("30.8")
    assert result.recommended_quantity == 21


def test_reorder_never_recommends_negative_quantity():
    result = calculate_reorder(
        average_7d=Decimal("1"),
        average_30d=Decimal("1"),
        current_stock=Decimal("100"),
        incoming_stock=Decimal("0"),
        safety_stock=Decimal("5"),
        lead_time_days=7,
    )
    assert result.recommended_quantity == 0


def test_reorder_clamps_negative_demand():
    result = calculate_reorder(
        average_7d=Decimal("-2"),
        average_30d=Decimal("-1"),
        current_stock=Decimal("0"),
        incoming_stock=Decimal("0"),
        safety_stock=Decimal("0"),
        lead_time_days=7,
    )
    assert result.daily_demand == 0
    assert result.recommended_quantity == 0


def test_reorder_uses_90_day_history_when_available():
    result = calculate_reorder(
        average_7d=Decimal("5"),
        average_30d=Decimal("3"),
        average_90d=Decimal("2"),
        current_stock=Decimal("0"),
        incoming_stock=Decimal("0"),
        safety_stock=Decimal("0"),
        lead_time_days=10,
        history_days=90,
    )
    assert result.daily_demand == Decimal("3.8")
    assert result.method == "weighted_moving_average_7_30_90"


def test_recent_product_uses_recent_average():
    result = calculate_reorder(
        average_7d=Decimal("4"),
        average_30d=Decimal("1"),
        current_stock=Decimal("0"),
        incoming_stock=Decimal("0"),
        safety_stock=Decimal("0"),
        lead_time_days=2,
        history_days=14,
    )
    assert result.daily_demand == Decimal("4")
    assert result.method == "recent_moving_average"


def test_count_variance_threshold_uses_historical_average():
    assert count_variance_threshold([]) == Decimal("2")
    assert count_variance_threshold(
        [Decimal("1"), Decimal("2"), Decimal("3")]
    ) == Decimal("6")
