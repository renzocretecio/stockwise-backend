from pydantic import BaseModel, Field, field_validator
from typing import Optional
from decimal import Decimal
from enum import Enum
from datetime import datetime


class SaleStatus(str, Enum):
    COMPLETED = "completed"
    VOIDED = "voided"


class PaymentMethod(str, Enum):
    CASH = "cash"
    CARD = "card"
    GCASH = "gcash"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class SaleItemCreate(BaseModel):
    """A single line item in a sale"""
    product_id: str
    quantity: Decimal = Field(..., gt=0, description="Quantity being sold")
    unit_price: Decimal = Field(..., ge=0, description="Selling price per unit")

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "product-uuid",
                "quantity": "3",
                "unit_price": "75000.00"
            }
        }


class SaleCreate(BaseModel):
    """Schema for creating a new sale"""
    reference_number: Optional[str] = Field(None, max_length=100)
    items: list[SaleItemCreate] = Field(..., min_length=1)
    payment_method: PaymentMethod = PaymentMethod.CASH
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: Optional[str] = None

    @field_validator("items")
    @classmethod
    def validate_unique_products(cls, v: list[SaleItemCreate]) -> list[SaleItemCreate]:
        product_ids = [item.product_id for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate product_id in sale items")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "reference_number": "INV-2026-001",
                "items": [
                    {"product_id": "product-uuid-1", "quantity": "2", "unit_price": "75000.00"},
                    {"product_id": "product-uuid-2", "quantity": "1", "unit_price": "1000.00"}
                ],
                "payment_method": "cash",
                "tax_amount": "0",
                "discount_amount": "500.00",
                "notes": "Walk-in customer"
            }
        }


class SaleVoidRequest(BaseModel):
    """Schema for voiding a sale"""
    reason: str = Field(..., min_length=1, max_length=500)


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class SaleItemResponse(BaseModel):
    """Sale line item response"""
    id: str
    product_id: str
    product_name: str
    sku: Optional[str] = None
    quantity: float
    unit_price: float
    unit_cost: float
    line_total: float
    line_profit: float

    class Config:
        from_attributes = True


class SaleResponse(BaseModel):
    """Complete sale response"""
    id: str
    reference_number: Optional[str] = None
    status: str
    payment_method: str
    items: list[SaleItemResponse]
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    total_profit: float
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None

    class Config:
        from_attributes = True


class SaleListItem(BaseModel):
    """Lightweight sale for list views"""
    id: str
    reference_number: Optional[str] = None
    status: str
    payment_method: str
    total_amount: float
    item_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class SalesResponse(BaseModel):
    """List sales response"""
    success: bool = True
    sales: list[SaleListItem]
    pagination: PaginationMeta


class SaleCreateResponse(BaseModel):
    """Sale creation response"""
    success: bool = True
    sale_id: str
    status: str
    total_amount: float
    message: str


class SaleVoidResponse(BaseModel):
    """Sale void response"""
    success: bool = True
    sale_id: str
    status: str
    message: str