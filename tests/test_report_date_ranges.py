from datetime import date

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routes.reports import _validate_export_range
from app.schemas.intelligence import ReportSummaryRequest
from app.services.report import ReportService


@pytest.mark.parametrize(
    "report_name",
    ["sales", "purchases", "profit", "stock-movements"],
)
def test_period_report_exports_accept_custom_date_range(report_name):
    _validate_export_range(
        report_name,
        date(2026, 8, 1),
        date(2026, 8, 31),
    )


@pytest.mark.parametrize("report_name", ["inventory", "low-stock"])
def test_snapshot_report_exports_reject_custom_date_range(report_name):
    with pytest.raises(HTTPException) as error:
        _validate_export_range(
            report_name,
            date(2026, 8, 1),
            date(2026, 8, 31),
        )

    assert error.value.status_code == 422
    assert error.value.detail == (
        "This report is a current inventory snapshot."
    )


def test_report_summary_accepts_custom_date_range():
    request = ReportSummaryRequest(
        report="sales",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    assert request.start_date == date(2026, 8, 1)
    assert request.end_date == date(2026, 8, 31)


def test_report_summary_rejects_partial_date_range():
    with pytest.raises(ValidationError):
        ReportSummaryRequest(
            report="sales",
            start_date=date(2026, 8, 1),
        )


def test_report_period_uses_business_timezone_boundaries():
    start, end, days, _ = ReportService._resolve_period(
        days=30,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
        timezone_name="Asia/Manila",
    )

    assert start.isoformat() == "2026-07-31T16:00:00+00:00"
    assert end is not None
    assert end.isoformat() == "2026-08-02T16:00:00+00:00"
    assert days == 2
