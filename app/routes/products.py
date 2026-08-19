from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.product import ProductService
from app.schemas.product import (
    ProductCreate,
    ProductsResponse,
)

router = APIRouter(prefix="/products", tags=["products"])

# CREATE PRODUCT
@router.post("")
async def create_product(
    payload: ProductCreate,
    context: RequestContext = Depends(require_permission("products.create")),
    db: Session = Depends(get_db),
):
    """Create a new product"""
    try:
        product = ProductService.create_product(
            business_id=str(context.business_id),
            payload=payload,
            db=db
        )

        return {
            "success": True,
            "product_id": product["id"],
            "message": f"Product '{product['name']}' created successfully"
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# LIST PRODUCTS
@router.get("", response_model=ProductsResponse)
async def list_products(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search by name, SKU, or barcode"),
    category: str | None = Query(default=None, description="Filter by category"),
    context: RequestContext = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Get paginated products for a business"""
    products, total = ProductService.get_products(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return {
        "success": True,
        "products": [
            ProductService._format_product_response(p) for p in products
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


# GET SINGLE PRODUCT
@router.get("/{product_id}")
async def get_product(
    product_id: str,
    context: RequestContext = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Get product details"""
    try:
        product = ProductService.get_product(
            business_id=str(context.business_id),
            product_id=product_id,
            db=db
        )
        
        return {
            "success": True,
            "product": product
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# UPDATE PRODUCT
@router.put("/{product_id}")
async def update_product(
    product_id: str,
    payload: dict,
    context: RequestContext = Depends(require_permission("products.update")),
    db: Session = Depends(get_db),
):
    """Update a product"""
    try:
        product = ProductService.update_product(
            business_id=str(context.business_id),
            product_id=product_id,
            payload=payload,
            db=db
        )
        
        return {
            "success": True,
            "product": product
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# DELETE PRODUCT
@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    context: RequestContext = Depends(require_permission("products.delete")),
    db: Session = Depends(get_db),
):
    """Delete a product"""
    try:
        result = ProductService.soft_delete_product(
            business_id=str(context.business_id),
            product_id=product_id,
            db=db
        )
        
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))