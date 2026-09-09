from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models import Business
from app.services.stock import StockService
from pydantic import BaseModel
from decimal import Decimal
from app.config.permissions import RequestContext, require_permission

router = APIRouter(prefix="/stock", tags=["stock"])


class AdjustStockRequest(BaseModel):
    product_id: str
    quantity_adjustment: float
    reason: str


@router.post("/{business_id}/adjust")
async def adjust_stock(
    business_id: str,
    req: AdjustStockRequest,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("inventory.adjust")),
):
    _require_matching_business(business_id, context)
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    movement = StockService.adjust_stock(
        business_id,
        req.product_id,
        Decimal(str(req.quantity_adjustment)),
        req.reason,
        str(context.user.id),
        db,
    )
    return {"success": True, "movement": {"id": str(movement.id)}}


@router.post("/{business_id}/count/start")
async def start_physical_count(
    business_id: str,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("inventory.count")),
):
    _require_matching_business(business_id, context)
    count = StockService.create_physical_count(
        business_id,
        str(context.user.id),
        db,
    )
    return {
        "success": True,
        "count": {"id": str(count.id), "status": count.status},
    }


@router.post("/{business_id}/count/{count_id}/finalize")
async def finalize_count(
    business_id: str,
    count_id: str,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("inventory.count")),
):
    _require_matching_business(business_id, context)
    count = StockService.finalize_count(
        business_id,
        count_id,
        str(context.user.id),
        db,
    )
    return {
        "success": True,
        "count": {"id": str(count.id), "status": count.status},
    }


@router.get("/{business_id}/movements")
async def get_movements(
    business_id: str,
    product_id: str = None,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("inventory.read")),
):
    _require_matching_business(business_id, context)
    movements = StockService.get_stock_movements(
        business_id,
        product_id,
        100,
        db,
    )
    return {
        "success": True,
        "movements": [
            {
                "id": str(m.id),
                "product_id": str(m.product_id),
                "movement_type": m.movement_type,
                "quantity": float(m.quantity),
                "reason": m.reason,
                "created_at": m.created_at.isoformat(),
            }
            for m in movements
        ],
    }


def _require_matching_business(
    business_id: str,
    context: RequestContext,
) -> None:
    if str(context.business_id) != business_id:
        raise HTTPException(
            status_code=403,
            detail="The path does not match the active business",
        )
