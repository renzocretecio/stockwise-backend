import csv
import asyncio
from datetime import date
from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.routes.reports import audit_dashboard_pdf_export
from app.schemas.report import DashboardPdfExportRequest
from app.services.report_export import ReportExportService


def test_sales_csv_contains_report_sections_and_sanitizes_formulas():
    report = {
        "summary": {
            "total_sales": 1,
            "total_revenue": 120.5,
            "total_profit": 40.5,
            "total_items_sold": 2,
            "average_sale_value": 120.5,
            "voided_count": 0,
            "return_count": 0,
            "return_amount": 0,
        },
        "by_day": [
            {
                "date": "2026-09-09",
                "revenue": 120.5,
                "profit": 40.5,
                "sales_count": 1,
            }
        ],
        "top_products": [
            {
                "product_id": "product-id",
                "sku": None,
                "product_name": '=HYPERLINK("bad")',
                "quantity_sold": 2,
                "units_per_day": 0.067,
                "current_stock": 8,
                "days_of_stock_remaining": None,
                "revenue": 120.5,
                "profit": 40.5,
            }
        ],
        "slow_products": [],
    }

    content = ReportExportService.build_csv(
        "sales",
        report,
        business_name="Demo Store",
        currency_code="PHP",
        period_label="Last 30 days",
        generated_at="2026-09-09 10:00:00 PHT",
    )
    rows = list(csv.reader(StringIO(content.removeprefix("\ufeff"))))

    assert content.startswith("\ufeff")
    assert ["Report", "Sales report"] in rows
    assert ["Currency", "PHP"] in rows
    assert ["Top products"] in rows
    assert any("'=HYPERLINK" in cell for row in rows for cell in row)
    assert "null" not in content.lower()


def test_dashboard_pdf_export_is_audited():
    db = MagicMock()
    context = SimpleNamespace(
        business_id="business-id",
        user=SimpleNamespace(id="user-id"),
    )
    payload = DashboardPdfExportRequest(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    result = asyncio.run(
        audit_dashboard_pdf_export(
            payload=payload,
            context=context,
            db=db,
        )
    )

    audit_log = db.add.call_args.args[0]
    assert result == {"success": True}
    assert audit_log.action == "report.exported"
    assert audit_log.new_values == {
        "report": "dashboard",
        "format": "pdf",
        "period": "2026-08-01 to 2026-08-31",
    }
    db.commit.assert_called_once_with()


def test_dashboard_pdf_export_rejects_invalid_range():
    db = MagicMock()
    context = SimpleNamespace(
        business_id="business-id",
        user=SimpleNamespace(id="user-id"),
    )
    payload = DashboardPdfExportRequest(
        start_date=date(2026, 9, 1),
        end_date=date(2026, 8, 31),
    )

    try:
        asyncio.run(
            audit_dashboard_pdf_export(
                payload=payload,
                context=context,
                db=db,
            )
        )
    except HTTPException as error:
        assert error.status_code == 422
    else:
        raise AssertionError("Expected an invalid date range error")

    db.add.assert_not_called()
    db.commit.assert_not_called()
