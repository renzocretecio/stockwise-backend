from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from enum import Enum
from datetime import datetime


class AdjustmentReason(str, Enum):
    DAMAGE = "damage"
    SHRINKAGE = "shrinkage"
    EXPIRY = "expiry"
    FOUND = "found"
    CORRECTION = "correction"
    OTHER = "other"


class MovementType(str, Enum):
    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    DAMAGE = "damage"
    EXPIRED = "expired"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


# ---- Stock Overview ----

class StockOverviewItem(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    unit: str
    quantity: float
    reserved_quantity: float
    available_quantity: float
    average_cost: float
    stock_value: float
    reorder_point: float
    safety_stock: float
    status: str  # "in_stock" | "low_stock" | "out_of_stock"

    class Config:
        from_attributes = True


class StockOverviewSummary(BaseModel):
    total_products: int
    total_stock_value: float
    low_stock_count: int
    out_of_stock_count: int


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool


class StockOverviewResponse(BaseModel):
    success: bool = True
    items: list[StockOverviewItem]
    summary: StockOverviewSummary
    pagination: PaginationMeta


# ---- Stock Adjustments ----

class StockAdjustmentCreate(BaseModel):
    product_id: str
    quantity_change: Decimal = Field(..., description="Positive to increase, negative to decrease")
    reason: AdjustmentReason
    notes: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "product-uuid",
                "quantity_change": "-5",
                "reason": "damage",
                "notes": "Water damage from storage leak"
            }
        }


class StockAdjustmentResponse(BaseModel):
    success: bool = True
    product_id: str
    quantity_before: float
    quantity_after: float
    quantity_change: float
    message: str


# ---- Stock Movements ----

class StockMovementItem(BaseModel):
    id: str
    product_id: str
    product_name: str
    movement_type: str
    quantity_change: float
    unit_cost: Optional[float] = None
    reason: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StockMovementsResponse(BaseModel):
    success: bool = True
    movements: list[StockMovementItem]
    pagination: PaginationMeta