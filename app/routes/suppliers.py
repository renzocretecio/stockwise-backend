from fastapi import APIRouter, Depends
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
    context: RequestContext = Depends(require_permission("suppliers.read")),
    db: Session = Depends(get_db),
):
    """Get all suppliers for a business"""
    suppliers = SupplierService.get_suppliers(
        business_id=str(context.business_id),
        db=db,
    )

    return {
        "success": True,
        "suppliers": [
            SupplierService._format_supplier_response(s) for s in suppliers
        ],
        "total": len(suppliers),
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