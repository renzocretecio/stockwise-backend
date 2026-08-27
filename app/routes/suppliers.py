from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.supplier import SupplierService
from app.schemas.supplier import (
    SupplierCreate,
    SupplierUpdate,
    SupplierCreateResponse,
    SuppliersResponse,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("", response_model=SupplierCreateResponse)
async def create_supplier(
    payload: SupplierCreate,
    context: RequestContext = Depends(require_permission("suppliers.create")),
    db: Session = Depends(get_db),
):
    """Create a new supplier"""
    supplier = SupplierService.create_supplier(
        business_id=str(context.business_id),
        payload=payload,
        db=db,
    )

    return {
        "success": True,
        "supplier_id": supplier["id"],
        "message": f"Supplier '{supplier['name']}' created successfully",
    }


@router.get("", response_model=SuppliersResponse)
async def list_suppliers(
    page: int = Query(
        default=1,
        ge=1,
        description="Page number",
    ),
    page_size: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Items per page",
    ),
    search: str | None = Query(
        default=None,
        description="Search by name, contact, email, or phone",
    ),
    context: RequestContext = Depends(
        require_permission("suppliers.read")
    ),
    db: Session = Depends(get_db),
):
    """Get paginated suppliers for a business."""

    suppliers, total = SupplierService.get_suppliers(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        search=search,
    )

    total_pages = (
        (total + page_size - 1) // page_size
        if total > 0
        else 0
    )

    return {
        "success": True,
        "suppliers": [
            SupplierService._format_supplier_response(
                supplier
            )
            for supplier in suppliers
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }


@router.get("/{supplier_id}")
async def get_supplier(
    supplier_id: str,
    context: RequestContext = Depends(require_permission("suppliers.read")),
    db: Session = Depends(get_db),
):
    """Get supplier details"""
    supplier = SupplierService.get_supplier(
        business_id=str(context.business_id),
        supplier_id=supplier_id,
        db=db,
    )

    return {"success": True, "supplier": supplier}


@router.put("/{supplier_id}")
async def update_supplier(
    supplier_id: str,
    payload: SupplierUpdate,
    context: RequestContext = Depends(require_permission("suppliers.update")),
    db: Session = Depends(get_db),
):
    """Update a supplier"""
    supplier = SupplierService.update_supplier(
        business_id=str(context.business_id),
        supplier_id=supplier_id,
        payload=payload,
        db=db,
    )

    return {"success": True, "supplier": supplier}


@router.delete("/{supplier_id}")
async def delete_supplier(
    supplier_id: str,
    context: RequestContext = Depends(require_permission("suppliers.archive")),
    db: Session = Depends(get_db),
):
    """Delete a supplier"""
    result = SupplierService.soft_delete_supplier(
        business_id=str(context.business_id),
        supplier_id=supplier_id,
        db=db,
    )

    return result