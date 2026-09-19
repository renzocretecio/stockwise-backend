from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.models import AuditLog
from app.services.report import ReportService
from app.services.report_export import ReportExportService
from app.schemas.report import (
    DashboardPdfExportRequest,
    SalesReportResponse,
    PurchaseReportResponse,
    InventoryReportResponse,
    ProfitReportResponse,
    LowStockReportResponse,
    StockMovementReportResponse,
    OperationalMetricsResponse,
)

router = APIRouter(prefix="/reports", tags=["reports"])

ReportExportName = Literal[
    "sales",
    "purchases",
    "inventory",
    "profit",
    "low-stock",
    "stock-movements",
]


@router.get("/sales", response_model=SalesReportResponse)
async def sales_report(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Sales report — revenue, profit, top products, daily breakdown"""
    _validate_optional_date_range(start_date, end_date)

    result = ReportService.get_sales_report(
        business_id=str(context.business_id),
        days=days,
        db=db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=context.membership.business.timezone,
    )
    return result


@router.get(
    "/operations",
    response_model=OperationalMetricsResponse,
)
async def operational_metrics(
    start_date: date = Query(),
    end_date: date = Query(),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Operational KPIs calculated from verified transaction data."""
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date.",
        )
    if (end_date - start_date).days + 1 > 365:
        raise HTTPException(
            status_code=422,
            detail="The date range cannot exceed 365 days.",
        )

    return ReportService.get_operational_metrics(
        business_id=str(context.business_id),
        db=db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=context.membership.business.timezone,
    )


@router.get("/purchases", response_model=PurchaseReportResponse)
async def purchase_report(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Purchase report — spend, supplier breakdown, daily trend"""
    _validate_optional_date_range(start_date, end_date)
    result = ReportService.get_purchase_report(
        business_id=str(context.business_id),
        days=days,
        db=db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=context.membership.business.timezone,
    )
    return result


@router.get("/inventory", response_model=InventoryReportResponse)
async def inventory_report(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Inventory valuation report — stock value by category"""
    result = ReportService.get_inventory_report(
        business_id=str(context.business_id), db=db
    )
    return result


@router.get("/profit", response_model=ProfitReportResponse)
async def profit_report(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Profit report — margin and profit breakdown by product"""
    _validate_optional_date_range(start_date, end_date)
    result = ReportService.get_profit_report(
        business_id=str(context.business_id),
        days=days,
        db=db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=context.membership.business.timezone,
    )
    return result


@router.get("/low-stock", response_model=LowStockReportResponse)
async def low_stock_report(
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Low stock report — products at or below reorder point"""
    result = ReportService.get_low_stock_report(
        business_id=str(context.business_id), db=db
    )
    return result


@router.get("/stock-movements", response_model=StockMovementReportResponse)
async def stock_movement_report(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Stock movement report — summary by movement type"""
    _validate_optional_date_range(start_date, end_date)
    result = ReportService.get_stock_movement_report(
        business_id=str(context.business_id),
        days=days,
        db=db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=context.membership.business.timezone,
    )
    return result


@router.get(
    "/{report_name}/export",
    dependencies=[Depends(require_permission("reports.read"))],
)
async def export_report(
    report_name: ReportExportName,
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    context: RequestContext = Depends(require_permission("reports.export")),
    db: Session = Depends(get_db),
):
    """Download the selected report's calculated data as a safe CSV."""
    _validate_export_range(report_name, start_date, end_date)
    business = context.membership.business
    report = _load_export_report(
        report_name=report_name,
        business_id=str(context.business_id),
        days=days,
        start_date=start_date,
        end_date=end_date,
        timezone_name=business.timezone,
        db=db,
    )


    try:
        business_zone = ZoneInfo(business.timezone)
    except Exception:
        business_zone = ZoneInfo("UTC")
    generated_at = datetime.now(timezone.utc).astimezone(business_zone)
    period_label = _export_period_label(
        report_name,
        days,
        start_date,
        end_date,
    )
    content = ReportExportService.build_csv(
        report_name,
        report,
        business_name=business.name,
        currency_code=business.currency_code,
        period_label=period_label,
        generated_at=generated_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
    )
    db.add(
        AuditLog(
            business_id=context.business_id,
            user_id=context.user.id,
            action="report.exported",
            entity_type="report",
            entity_id=None,
            new_values={
                "report": report_name,
                "format": "csv",
                "period": period_label,
            },
        )
    )
    db.commit()

    filename = f"kitastock-{report_name}-{generated_at.date().isoformat()}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/dashboard/export-audit",
    dependencies=[Depends(require_permission("reports.read"))],
)
async def audit_dashboard_pdf_export(
    payload: DashboardPdfExportRequest,
    context: RequestContext = Depends(
        require_permission("reports.export")
    ),
    db: Session = Depends(get_db),
):
    """Authorize and record a client-rendered dashboard PDF export."""
    _validate_date_range(payload.start_date, payload.end_date)
    period_label = (
        f"{payload.start_date.isoformat()} to "
        f"{payload.end_date.isoformat()}"
    )
    db.add(
        AuditLog(
            business_id=context.business_id,
            user_id=context.user.id,
            action="report.exported",
            entity_type="report",
            entity_id=None,
            new_values={
                "report": "dashboard",
                "format": "pdf",
                "period": period_label,
            },
        )
    )
    db.commit()

    return {"success": True}


def _validate_export_range(
    report_name: ReportExportName,
    start_date: date | None,
    end_date: date | None,
) -> None:
    _validate_optional_date_range(start_date, end_date)
    if start_date is None or end_date is None:
        return
    if report_name in {"inventory", "low-stock"}:
        raise HTTPException(
            status_code=422,
            detail="This report is a current inventory snapshot.",
        )


def _validate_optional_date_range(
    start_date: date | None,
    end_date: date | None,
) -> None:
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="Both start_date and end_date are required.",
        )
    if start_date is not None and end_date is not None:
        _validate_date_range(start_date, end_date)


def _validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date.",
        )
    if (end_date - start_date).days + 1 > 366:
        raise HTTPException(
            status_code=422,
            detail="The date range cannot exceed 366 days.",
        )


def _load_export_report(
    *,
    report_name: ReportExportName,
    business_id: str,
    days: int,
    start_date: date | None,
    end_date: date | None,
    timezone_name: str,
    db: Session,
) -> dict:
    if report_name == "sales":
        return ReportService.get_sales_report(
            business_id=business_id,
            days=days,
            db=db,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
        )
    if report_name == "purchases":
        return ReportService.get_purchase_report(
            business_id,
            days,
            db,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
        )
    if report_name == "inventory":
        return ReportService.get_inventory_report(business_id, db)
    if report_name == "profit":
        return ReportService.get_profit_report(
            business_id,
            days,
            db,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
        )
    if report_name == "low-stock":
        return ReportService.get_low_stock_report(business_id, db)
    return ReportService.get_stock_movement_report(
        business_id,
        days,
        db,
        start_date=start_date,
        end_date=end_date,
        timezone_name=timezone_name,
    )


def _export_period_label(
    report_name: ReportExportName,
    days: int,
    start_date: date | None,
    end_date: date | None,
) -> str:
    if start_date is not None and end_date is not None:
        return f"{start_date.isoformat()} to {end_date.isoformat()}"
    if report_name in {"inventory", "low-stock"}:
        return "Current inventory"
    return f"Last {days} days"
