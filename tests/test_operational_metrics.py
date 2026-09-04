from decimal import Decimal

from app.services.report import ReportService


def test_operational_metrics_calculations():
    metrics = ReportService._build_operational_metrics(
        period_days=30,
        counted_items=10,
        accurate_items=9,
        inventory_value=Decimal("3000"),
        period_cogs=Decimal("1500"),
        shrinkage_units=Decimal("3"),
        shrinkage_value=Decimal("30"),
        ordered_purchases=4,
        received_purchases=3,
    )

    assert metrics["stock_accuracy_rate"] == 90.0
    assert metrics["inventory_days"] == 60.0
    assert metrics["shrinkage_rate"] == 1.0
    assert metrics["receipt_completion_rate"] == 75.0


def test_operational_metrics_marks_missing_denominators_unavailable():
    metrics = ReportService._build_operational_metrics(
        period_days=30,
        counted_items=0,
        accurate_items=0,
        inventory_value=Decimal("0"),
        period_cogs=Decimal("0"),
        shrinkage_units=Decimal("0"),
        shrinkage_value=Decimal("0"),
        ordered_purchases=0,
        received_purchases=0,
    )

    assert metrics["stock_accuracy_rate"] is None
    assert metrics["inventory_days"] is None
    assert metrics["shrinkage_rate"] is None
    assert metrics["receipt_completion_rate"] is None
