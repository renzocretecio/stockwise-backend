from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from enum import Enum
from datetime import datetime


class CountScope(str, Enum):
    ALL = "all"
    CATEGORY = "category"
    CUSTOM = "custom"


class CountStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# ---- Create Count ----

class InventoryCountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scope: CountScope = CountScope.ALL
    category: Optional[str] = None
    product_ids: Optional[list[str]] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Q3 2026 Full Count",
                "scope": "all"
            }
        }


class InventoryCountItemPreview(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    expected_quantity: float
    counted_quantity: Optional[float] = None
    variance: Optional[float] = None

    class Config:
        from_attributes = True


class InventoryCountCreateResponse(BaseModel):
    success: bool = True
    inventory_count_id: str
    name: str
    status: str
    total_items: int
    message: str


# ---- Record Count Item ----

class RecordCountItem(BaseModel):
    product_id: str
    counted_quantity: Decimal = Field(..., ge=0)
    notes: Optional[str] = None


class RecordCountItems(BaseModel):
    items: list[RecordCountItem]


class RecordCountItemResult(BaseModel):
    product_id: str
    expected_quantity: float
    counted_quantity: float
    variance: float


class RecordCountItemsResponse(BaseModel):
    success: bool = True
    count_id: str
    updated_items: int
    items: list[RecordCountItemResult]


# ---- Get Count Detail ----

class InventoryCountDetail(BaseModel):
    id: str
    name: str
    status: str
    scope: str
    total_items: int
    counted_items: int
    items_with_variance: int
    created_at: datetime
    finalized_at: Optional[datetime] = None
    items: list[InventoryCountItemPreview]

    class Config:
        from_attributes = True


class InventoryCountDetailResponse(BaseModel):
    success: bool = True
    count: InventoryCountDetail


# ---- List Counts ----

class InventoryCountListItem(BaseModel):
    id: str
    name: str
    status: str
    total_items: int
    counted_items: int
    created_at: datetime
    finalized_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InventoryCountsResponse(BaseModel):
    success: bool = True
    counts: list[InventoryCountListItem]


# ---- Finalize ----

class FinalizeCountResponse(BaseModel):
    success: bool = True
    count_id: str
    status: str
    adjustments_made: int
    message: str