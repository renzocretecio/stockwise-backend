from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.inventory_count import InventoryCountService
from app.schemas.inventory_count import (
    InventoryCountCreate,
    RecordCountItemsResponse,
    InventoryCountCreateResponse,
    InventoryCountDetailResponse,
    InventoryCountsResponse,
    RecordCountItems,
    FinalizeCountResponse,
)

router = APIRouter(prefix="/inventory-counts", tags=["inventory-counts"])


@router.post("", response_model=InventoryCountCreateResponse)
async def start_count(
    payload: InventoryCountCreate,
    context: RequestContext = Depends(require_permission("inventory.count")),
    db: Session = Depends(get_db),
):
    """Start a new physical count session"""
    result = InventoryCountService.create_count(
        business_id=str(context.business_id),
        payload=payload,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}


@router.get("", response_model=InventoryCountsResponse)
async def list_counts(
    context: RequestContext = Depends(require_permission("inventory.count")),
    db: Session = Depends(get_db),
):
    """List all count sessions"""
    counts = InventoryCountService.get_counts(
        business_id=str(context.business_id), db=db
    )
    return {"success": True, "counts": counts}


@router.get("/{count_id}", response_model=InventoryCountDetailResponse)
async def get_count(
    count_id: str,
    context: RequestContext = Depends(require_permission("inventory.count")),
    db: Session = Depends(get_db),
):
    """Get count session detail with items and variances"""
    count = InventoryCountService.get_count_detail(
        business_id=str(context.business_id), count_id=count_id, db=db
    )
    return {"success": True, "count": count}


@router.post(
    "/{count_id}/record",
    response_model=RecordCountItemsResponse,
)
async def record_count_items(
    count_id: str,
    payload: RecordCountItems,
    context: RequestContext = Depends(
        require_permission("inventory.count")
    ),
    db: Session = Depends(get_db),
):
    """Record counted quantities for multiple products."""

    result = InventoryCountService.record_count_items(
        business_id=str(context.business_id),
        count_id=count_id,
        items=payload.items,
        user_id=str(context.user.id),
        db=db,
    )

    return {
        "success": True,
        **result,
    }


@router.post("/{count_id}/finalize", response_model=FinalizeCountResponse)
async def finalize_count(
    count_id: str,
    context: RequestContext = Depends(require_permission("inventory.count")),
    db: Session = Depends(get_db),
):
    """Finalize count, applying variances as stock movements"""
    result = InventoryCountService.finalize_count(
        business_id=str(context.business_id),
        count_id=count_id,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}


@router.post("/{count_id}/cancel")
async def cancel_count(
    count_id: str,
    context: RequestContext = Depends(require_permission("inventory.count")),
    db: Session = Depends(get_db),
):
    """Cancel an in-progress count"""
    result = InventoryCountService.cancel_count(
        business_id=str(context.business_id), count_id=count_id, db=db
    )
    return result