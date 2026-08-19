from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.report import ReportService
from app.schemas.report import (
    SalesReportResponse,
    PurchaseReportResponse,
    InventoryReportResponse,
    ProfitReportResponse,
    LowStockReportResponse,
    StockMovementReportResponse,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/sales", response_model=SalesReportResponse)
async def sales_report(
    days: int = Query(default=30, ge=1, le=365),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Sales report — revenue, profit, top products, daily breakdown"""
    result = ReportService.get_sales_report(
        business_id=str(context.business_id), days=days, db=db
    )
    return result


@router.get("/purchases", response_model=PurchaseReportResponse)
async def purchase_report(
    days: int = Query(default=30, ge=1, le=365),
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Purchase report — spend, supplier breakdown, daily trend"""
    result = ReportService.get_purchase_report(
        business_id=str(context.business_id), days=days, db=db
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
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Profit report — margin and profit breakdown by product"""
    result = ReportService.get_profit_report(
        business_id=str(context.business_id), days=days, db=db
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
    context: RequestContext = Depends(require_permission("reports.read")),
    db: Session = Depends(get_db),
):
    """Stock movement report — summary by movement type"""
    result = ReportService.get_stock_movement_report(
        business_id=str(context.business_id), days=days, db=db
    )
    return result