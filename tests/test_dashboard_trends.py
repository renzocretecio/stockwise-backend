from datetime import date

from app.services.dashboard_trends import (
    trend_bucket_start,
    trend_granularity,
)


def test_trend_granularity_uses_readable_intervals():
    assert trend_granularity(30) == "day"
    assert trend_granularity(90) == "week"
    assert trend_granularity(365) == "month"


def test_week_bucket_starts_on_monday():
    assert trend_bucket_start(date(2026, 9, 3), "week") == date(
        2026, 8, 31
    )


def test_month_bucket_starts_on_first_day():
    assert trend_bucket_start(date(2026, 9, 18), "month") == date(
        2026, 9, 1
    )
