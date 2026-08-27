from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.sale import SaleService
from app.schemas.sale import (
    SaleCreate,
    SaleVoidRequest,
    SaleCreateResponse,
    SaleVoidResponse,
    SaleResponse,
    SalesResponse,
    SaleReturnCreate,
    SaleReturnResponse,
    SaleReturnsResponse,
)

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post("", response_model=SaleCreateResponse)
async def create_sale(
    payload: SaleCreate,
    context: RequestContext = Depends(require_permission("sales.create")),
    db: Session = Depends(get_db),
):
    """Create a new sale — validates and deducts stock"""
    result = SaleService.create_sale(
        business_id=str(context.business_id),
        payload=payload,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}


@router.post("/{sale_id}/returns", response_model=SaleReturnResponse)
async def create_return(
    sale_id: str,
    payload: SaleReturnCreate,
    context: RequestContext = Depends(require_permission("sales.void")),
    db: Session = Depends(get_db),
):
    """Create a partial or complete return and restore eligible stock."""
    result = SaleService.create_return(
        business_id=str(context.business_id),
        sale_id=sale_id,
        payload=payload,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}


@router.get("", response_model=SalesResponse)
async def list_sales(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    payment_method: str | None = Query(default=None),
    context: RequestContext = Depends(require_permission("sales.read")),
    db: Session = Depends(get_db),
):
    """List all sales for a business"""
    result = SaleService.get_sales(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        payment_method=payment_method,
    )
    return {"success": True, **result}


@router.get("/returns", response_model=SaleReturnsResponse)
async def list_returns(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    context: RequestContext = Depends(require_permission("sales.read")),
    db: Session = Depends(get_db),
):
    """List completed and cancelled sale returns for a business."""
    result = SaleService.get_returns(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        search=search,
    )
    return {"success": True, **result}


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: str,
    context: RequestContext = Depends(require_permission("sales.read")),
    db: Session = Depends(get_db),
):
    """Get sale details"""
    sale = SaleService.get_sale(
        business_id=str(context.business_id),
        sale_id=sale_id,
        db=db,
    )
    return sale


@router.post("/{sale_id}/void", response_model=SaleVoidResponse)
async def void_sale(
    sale_id: str,
    payload: SaleVoidRequest,
    context: RequestContext = Depends(require_permission("sales.void")),
    db: Session = Depends(get_db),
):
    """Void a sale — restores stock"""
    result = SaleService.void_sale(
        business_id=str(context.business_id),
        sale_id=sale_id,
        reason=payload.reason if payload else None,
        user_id=str(context.user.id),
        db=db,
    )
    return {"success": True, **result}
