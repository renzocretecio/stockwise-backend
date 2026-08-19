from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.stock import StockService
from app.schemas.stock import (
    StockAdjustmentCreate,
    StockOverviewResponse,
    StockMovementsResponse,
    StockAdjustmentResponse,
)

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/overview", response_model=StockOverviewResponse)
async def stock_overview(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    context: RequestContext = Depends(require_permission("inventory.read")),
    db: Session = Depends(get_db),
):
    """Get current stock levels across all products"""
    result = StockService.get_stock_overview(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        status_filter=status_filter,
    )
    return {"success": True, **result}


@router.get("/movements", response_model=StockMovementsResponse)
async def stock_movements(
    product_id: str | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    context: RequestContext = Depends(require_permission("inventory.read")),
    db: Session = Depends(get_db),
):
    """Get stock movement history / audit trail"""
    result = StockService.get_stock_movements(
        business_id=str(context.business_id),
        db=db,
        product_id=product_id,
        movement_type=movement_type,
        page=page,
        page_size=page_size,
    )
    return {"success": True, **result}


@router.post("/adjustments", response_model=StockAdjustmentResponse)
async def adjust_stock(
    payload: StockAdjustmentCreate,
    context: RequestContext = Depends(require_permission("inventory.adjust")),
    db: Session = Depends(get_db),
):
    """Manually adjust stock (damage, loss, found, correction, etc.)"""
    result = StockService.adjust_stock(
        business_id=str(context.business_id),
        payload=payload,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}