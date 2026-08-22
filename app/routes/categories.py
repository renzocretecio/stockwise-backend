from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import require_permission, RequestContext
from app.services.category import CategoryService
from app.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryCreateResponse,
    CategoriesResponse,
)

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("/all")
async def list_all_categories(
    context: RequestContext = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Get all categories, unpaginated — for dropdowns/selects"""
    categories, total = CategoryService.get_categories(
        business_id=str(context.business_id),
        db=db,
        paginate=False,
    )

    return {
        "success": True,
        "categories": [
            CategoryService._format_category_response(c) for c in categories
        ],
        "total": total,
    }

@router.post("", response_model=CategoryCreateResponse)
async def create_category(
    payload: CategoryCreate,
    context: RequestContext = Depends(require_permission("products.create")),
    db: Session = Depends(get_db),
):
    """Create a new category"""
    category = CategoryService.create_category(
        business_id=str(context.business_id),
        payload=payload,
        db=db,
    )

    return {
        "success": True,
        "category_id": category["id"],
        "message": f"Category '{category['name']}' created successfully",
    }


@router.get("", response_model=CategoriesResponse)
async def list_categories(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(default=None, description="Search by name, SKU, or barcode"),
    context: RequestContext = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Get all categories for a business"""
    categories, total = CategoryService.get_categories(
        business_id=str(context.business_id),
        db=db,
        page=page,
        page_size=page_size,
        search=search,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return {
        "success": True,
        "categories": categories,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
    }


@router.get("/{category_id}")
async def get_category(
    category_id: str,
    context: RequestContext = Depends(require_permission("products.read")),
    db: Session = Depends(get_db),
):
    """Get category details"""
    category = CategoryService.get_category(
        business_id=str(context.business_id),
        category_id=category_id,
        db=db,
    )

    return {"success": True, "category": category}


@router.put("/{category_id}")
async def update_category(
    category_id: str,
    payload: CategoryUpdate,
    context: RequestContext = Depends(require_permission("products.update")),
    db: Session = Depends(get_db),
):
    """Update a category"""
    category = CategoryService.update_category(
        business_id=str(context.business_id),
        category_id=category_id,
        payload=payload,
        db=db,
    )

    return {"success": True, "category": category}


@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    context: RequestContext = Depends(require_permission("products.archive")),
    db: Session = Depends(get_db),
):
    """Delete a category"""
    result = CategoryService.soft_delete_category(
        business_id=str(context.business_id),
        category_id=category_id,
        db=db,
    )

    return result