from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.schemas.storefront import (
    PublicOrderCreate,
    StoreOrderStatus,
    StoreOrderStatusUpdate,
    StoreProductBulkPublish,
    StoreProductUpdate,
    StorefrontCreate,
    StorefrontUpdate,
)
from app.services.storefront import StorefrontService


router = APIRouter(prefix="/storefront", tags=["storefront"])
public_router = APIRouter(prefix="/public", tags=["public storefront"])


@router.post("")
async def create_storefront(
    payload: StorefrontCreate,
    context: RequestContext = Depends(require_permission("storefront.manage")),
    db: Session = Depends(get_db),
):
    return StorefrontService.create_store(
        context.business_id,
        payload,
        db,
    )


@router.get("")
async def get_storefront(
    context: RequestContext = Depends(require_permission("storefront.read")),
    db: Session = Depends(get_db),
):
    return StorefrontService.get_store(context.business_id, db)


@router.patch("")
async def update_storefront(
    payload: StorefrontUpdate,
    context: RequestContext = Depends(require_permission("storefront.manage")),
    db: Session = Depends(get_db),
):
    return StorefrontService.update_store(
        context.business_id,
        payload,
        db,
    )


@router.get("/products")
async def list_storefront_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    context: RequestContext = Depends(require_permission("storefront.read")),
    db: Session = Depends(get_db),
):
    return StorefrontService.list_catalog_products(
        context.business_id,
        db,
        page,
        page_size,
        search,
    )


@router.put("/products/{product_id}")
async def update_storefront_product(
    product_id: UUID,
    payload: StoreProductUpdate,
    context: RequestContext = Depends(require_permission("storefront.manage")),
    db: Session = Depends(get_db),
):
    return StorefrontService.update_catalog_product(
        context.business_id,
        product_id,
        payload,
        db,
    )


@router.put("/products")
async def bulk_publish_storefront_products(
    payload: StoreProductBulkPublish,
    context: RequestContext = Depends(require_permission("storefront.manage")),
    db: Session = Depends(get_db),
):
    return StorefrontService.bulk_publish_catalog_products(
        context.business_id,
        payload,
        db,
    )


@router.get("/orders")
async def list_storefront_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: StoreOrderStatus
    | None = Query(
        default=None,
        alias="status",
    ),
    search: str | None = Query(default=None, max_length=200),
    context: RequestContext = Depends(require_permission("storefront.read")),
    db: Session = Depends(get_db),
):
    return StorefrontService.list_orders(
        context.business_id,
        db,
        page,
        page_size,
        status_filter.value if status_filter else None,
        search,
    )


@router.get("/orders/{order_id}")
async def get_storefront_order(
    order_id: UUID,
    context: RequestContext = Depends(require_permission("storefront.read")),
    db: Session = Depends(get_db),
):
    return StorefrontService.get_order(
        context.business_id,
        order_id,
        db,
    )


@router.post("/orders/{order_id}/status")
async def update_storefront_order_status(
    order_id: UUID,
    payload: StoreOrderStatusUpdate,
    context: RequestContext = Depends(require_permission("storefront.orders")),
    db: Session = Depends(get_db),
):
    return StorefrontService.update_order_status(
        context.business_id,
        order_id,
        payload,
        context.user.id,
        db,
    )


@public_router.get("/stores/{slug}")
async def get_public_store(
    slug: str,
    db: Session = Depends(get_db),
):
    return StorefrontService.get_public_store(slug, db)


@public_router.get("/stores/{slug}/products")
async def list_public_store_products(
    slug: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    category_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return StorefrontService.list_public_products(
        slug,
        db,
        page,
        page_size,
        search,
        category_id,
    )


@public_router.get("/stores/{slug}/categories")
async def list_public_store_categories(
    slug: str,
    db: Session = Depends(get_db),
):
    return StorefrontService.list_public_categories(slug, db)


@public_router.post("/stores/{slug}/orders", status_code=201)
async def create_public_store_order(
    slug: str,
    payload: PublicOrderCreate,
    db: Session = Depends(get_db),
):
    return StorefrontService.create_public_order(slug, payload, db)


@public_router.get("/orders/{reference_number}")
async def get_public_store_order(
    reference_number: str,
    token: str = Query(..., min_length=20, max_length=100),
    db: Session = Depends(get_db),
):
    return StorefrontService.get_public_order(
        reference_number,
        token,
        db,
    )
