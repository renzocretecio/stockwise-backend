from pydantic import BaseModel, Field, field_validator
from typing import Optional
from decimal import Decimal
from enum import Enum
from datetime import datetime


class PurchaseStatus(str, Enum):
    DRAFT = "draft"
    ORDERED = "ordered"
    RECEIVED = "received"
    CANCELLED = "cancelled"


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class PurchaseItemCreate(BaseModel):
    """A single line item in a purchase"""
    product_id: str
    quantity: Decimal = Field(..., gt=0, description="Quantity being purchased")
    unit_cost: Decimal = Field(..., ge=0, description="Cost per unit")

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "product-uuid",
                "quantity": "50",
                "unit_cost": "120.00"
            }
        }


class PurchaseCreate(BaseModel):
    """Schema for creating a new purchase draft"""
    supplier_id: str
    reference_number: Optional[str] = Field(None, max_length=100)
    items: list[PurchaseItemCreate] = Field(..., min_length=1)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: Optional[str] = None

    @field_validator("items")
    @classmethod
    def validate_unique_products(cls, v: list[PurchaseItemCreate]) -> list[PurchaseItemCreate]:
        product_ids = [item.product_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate product_id in purchase items")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "supplier_id": "supplier-uuid",
                "reference_number": "PO-2026-001",
                "items": [
                    {"product_id": "product-uuid-1", "quantity": "50", "unit_cost": "120.00"},
                    {"product_id": "product-uuid-2", "quantity": "20", "unit_cost": "45.50"}
                ],
                "tax_amount": "50.00",
                "discount_amount": "0",
                "notes": "Monthly restock order"
            }
        }


class PurchaseUpdate(BaseModel):
    """Schema for updating a draft purchase (before receiving)"""
    supplier_id: Optional[str] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    items: Optional[list[PurchaseItemCreate]] = Field(None, min_length=1)
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    discount_amount: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class PurchaseItemResponse(BaseModel):
    """Purchase line item response"""
    id: str
    product_id: str
    product_name: str
    sku: Optional[str] = None
    quantity: float
    unit_cost: float
    line_total: float

    class Config:
        from_attributes = True


class PurchaseResponse(BaseModel):
    """Complete purchase response"""
    id: str
    supplier_id: str
    supplier_name: str
    reference_number: Optional[str] = None
    status: str
    items: list[PurchaseItemResponse]
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    ordered_at: Optional[datetime] = None
    received_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class PurchaseListItemProduct(BaseModel):
    id: str
    product_id: str
    product_name: str
    sku: Optional[str] = None
    quantity: float
    unit_cost: float
    line_total: float

    class Config:
        from_attributes = True

class PurchaseListItem(BaseModel):
    """Lightweight purchase for list views."""

    id: str
    supplier_id: str
    supplier_name: str
    reference_number: Optional[str] = None
    status: str
    total_amount: float
    item_count: int
    items: list[PurchaseListItemProduct]
    created_at: datetime
    ordered_at: Optional[datetime] = None
    received_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PurchasesResponse(BaseModel):
    """List purchases response"""
    success: bool = True
    purchases: list[PurchaseListItem]
    pagination: PaginationMeta


class PurchaseCreateResponse(BaseModel):
    """Purchase creation response"""
    success: bool = True
    purchase_id: str
    status: str
    total_amount: float
    message: str


class PurchaseOrderResponse(BaseModel):
    success: bool = True
    purchase_id: str
    status: str
    message: str


class PurchaseReceiveResponse(BaseModel):
    """Purchase receiving response"""
    success: bool = True
    purchase_id: str
    status: str
    items_received: int
    message: str


class PurchaseCancelResponse(BaseModel):
    """Purchase cancellation response"""
    success: bool = True
    purchase_id: str
    status: str
    message: str
