from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.report import ReportService


def record(**values):
    return SimpleNamespace(**values)


def test_sales_report_subtracts_completed_returns():
    sale = record(
        id="sale-1",
        total_amount=Decimal("200"),
        sale_date=datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
    )
    sale_item = record(
        sale_id="sale-1",
        product_id="product-1",
        quantity=Decimal("2"),
        unit_price=Decimal("100"),
        unit_cost=Decimal("60"),
        line_total=Decimal("200"),
    )
    sale_return = record(
        id="return-1",
        refund_amount=Decimal("100"),
        created_at=datetime(2026, 9, 2, 8, tzinfo=timezone.utc),
    )
    return_item = record(
        return_id="return-1",
        product_id="product-1",
        quantity=Decimal("1"),
        unit_cost=Decimal("60"),
        refund_amount=Decimal("100"),
    )

    report = ReportService._build_sales_report(
        days=30,
        completed_sales=[sale],
        voided_sales=[],
        sale_items=[sale_item],
        completed_returns=[sale_return],
        return_items=[return_item],
        product_names={"product-1": "Wireless Earbuds"},
    )

    assert report["summary"] == {
        "total_sales": 1,
        "total_revenue": 100.0,
        "total_profit": 40.0,
        "total_items_sold": 1.0,
        "average_sale_value": 100.0,
        "voided_count": 0,
    }
    assert report["by_day"] == [
        {
            "date": "2026-09-01",
            "revenue": 200.0,
            "profit": 80.0,
            "sales_count": 1,
        },
        {
            "date": "2026-09-02",
            "revenue": -100.0,
            "profit": -40.0,
            "sales_count": 0,
        },
    ]
    assert report["top_products"] == [
        {
            "product_id": "product-1",
            "product_name": "Wireless Earbuds",
            "quantity_sold": 1.0,
            "revenue": 100.0,
            "profit": 40.0,
        }
    ]


def test_sales_report_excludes_fully_returned_product_from_top_products():
    sale = record(
        id="sale-1",
        total_amount=Decimal("25"),
        sale_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    sale_item = record(
        sale_id="sale-1",
        product_id="product-1",
        quantity=Decimal("1"),
        unit_price=Decimal("25"),
        unit_cost=Decimal("10"),
        line_total=Decimal("25"),
    )
    sale_return = record(
        id="return-1",
        refund_amount=Decimal("25"),
        created_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    return_item = record(
        return_id="return-1",
        product_id="product-1",
        quantity=Decimal("1"),
        unit_cost=Decimal("10"),
        refund_amount=Decimal("25"),
    )

    report = ReportService._build_sales_report(
        days=30,
        completed_sales=[sale],
        voided_sales=[],
        sale_items=[sale_item],
        completed_returns=[sale_return],
        return_items=[return_item],
        product_names={"product-1": "USB Cable"},
    )

    assert report["summary"]["total_revenue"] == 0
    assert report["summary"]["total_profit"] == 0
    assert report["summary"]["total_items_sold"] == 0
    assert report["top_products"] == []


def test_sales_report_groups_days_in_business_timezone():
    sale = record(
        id="sale-1",
        total_amount=Decimal("50"),
        sale_date=datetime(2026, 9, 1, 16, 30, tzinfo=timezone.utc),
    )

    report = ReportService._build_sales_report(
        days=1,
        completed_sales=[sale],
        voided_sales=[],
        sale_items=[],
        completed_returns=[],
        return_items=[],
        product_names={},
        timezone_name="Asia/Manila",
    )

    assert report["by_day"][0]["date"] == "2026-09-02"


def test_product_velocity_uses_available_stock_and_period_days():
    products = [{
        "product_id": "product-1",
        "quantity_sold": 15.0,
    }]
    product = record(sku="EAR-001")
    balance = record(
        quantity=Decimal("20"),
        reserved_quantity=Decimal("5"),
    )

    ReportService._add_product_velocity(
        products=products,
        products_by_id={"product-1": product},
        stock_by_product={"product-1": balance},
        period_days=30,
    )

    assert products[0]["sku"] == "EAR-001"
    assert products[0]["units_per_day"] == 0.5
    assert products[0]["current_stock"] == 15.0
    assert products[0]["days_of_stock_remaining"] == 30.0
