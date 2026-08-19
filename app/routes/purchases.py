from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.purchase import PurchaseService
from app.schemas.purchase import (
    PurchaseCreate,
    PurchaseUpdate,
    PurchaseCreateResponse,
    PurchaseReceiveResponse,
    PurchaseCancelResponse,
    PurchaseResponse,
    PurchasesResponse,
)

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.post("", response_model=PurchaseCreateResponse)
async def create_purchase(
    payload: PurchaseCreate,
    context: RequestContext = Depends(require_permission("purchases.create")),
    db: Session = Depends(get_db),
):
    """Create a new purchase draft"""
    result = PurchaseService.create_purchase(
        business_id=str(context.business_id),
        payload=payload,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}


@router.get("", response_model=PurchasesResponse)
async def list_purchases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    supplier_id: str | None = Query(default=None),
    context: RequestContext = Depends(require_permission("purchases.read")),
    db: Session = Depends(get_db),
):
    """List all purchases for a business"""
    result = PurchaseService.get_purchases(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        supplier_id=supplier_id,
    )
    return {"success": True, **result}


@router.get("/{purchase_id}", response_model=PurchaseResponse)
async def get_purchase(
    purchase_id: str,
    context: RequestContext = Depends(require_permission("purchases.read")),
    db: Session = Depends(get_db),
):
    """Get purchase details"""
    purchase = PurchaseService.get_purchase(
        business_id=str(context.business_id),
        purchase_id=purchase_id,
        db=db,
    )
    return purchase


@router.put("/{purchase_id}")
async def update_purchase(
    purchase_id: str,
    payload: PurchaseUpdate,
    context: RequestContext = Depends(require_permission("purchases.create")),
    db: Session = Depends(get_db),
):
    """Update a draft purchase (only allowed before receiving)"""
    result = PurchaseService.update_purchase(
        business_id=str(context.business_id),
        purchase_id=purchase_id,
        payload=payload,
        db=db,
    )
    return {"success": True, "purchase": result}


@router.post("/{purchase_id}/receive", response_model=PurchaseReceiveResponse)
async def receive_purchase(
    purchase_id: str,
    context: RequestContext = Depends(require_permission("purchases.receive")),
    db: Session = Depends(get_db),
):
    """Receive a purchase and update stock"""
    result = PurchaseService.receive_purchase(
        business_id=str(context.business_id),
        purchase_id=purchase_id,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}


@router.post("/{purchase_id}/cancel", response_model=PurchaseCancelResponse)
async def cancel_purchase(
    purchase_id: str,
    context: RequestContext = Depends(require_permission("purchases.cancel")),
    db: Session = Depends(get_db),
):
    """Cancel a draft purchase"""
    result = PurchaseService.cancel_purchase(
        business_id=str(context.business_id),
        purchase_id=purchase_id,
        db=db,
    )
    return {"success": True, **result}