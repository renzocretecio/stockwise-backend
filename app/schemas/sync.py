from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SyncMutation(BaseModel):
    client_event_id: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any]
    occurred_at: datetime


class SyncMutationResponse(BaseModel):
    success: bool = True
    duplicate: bool = False
    client_event_id: str
    type: str
    result: dict[str, Any] | None = None


class ReferenceProduct(BaseModel):
    id: UUID
    name: str
    sku: str | None = None
    barcode: str | None = None
    supplier_id: UUID | None = None
    category_id: UUID | None = None
    cost_price: Decimal
    selling_price: Decimal
    unit: str
    reorder_point: Decimal
    safety_stock: Decimal
    lead_time_days: int
    is_perishable: bool
    updated_at: datetime


class ReferenceSupplier(BaseModel):
    id: UUID
    name: str
    lead_time_days: int
    updated_at: datetime


class ReferenceSupplierProduct(BaseModel):
    product_id: UUID
    supplier_id: UUID
    supplier_sku: str | None = None
    unit_cost: Decimal
    lead_time_days: int
    minimum_order_quantity: Decimal
    pack_size: Decimal
    is_preferred: bool
    updated_at: datetime


class ReferenceCategory(BaseModel):
    id: UUID
    name: str
    updated_at: datetime


class ReferenceStockBalance(BaseModel):
    product_id: UUID
    quantity: Decimal
    reserved_quantity: Decimal
    average_cost: Decimal
    updated_at: datetime


class ReferenceDataResponse(BaseModel):
    success: bool = True
    business_id: UUID
    generated_at: datetime
    products: list[ReferenceProduct]
    suppliers: list[ReferenceSupplier]
    supplier_products: list[ReferenceSupplierProduct]
    categories: list[ReferenceCategory]
    stock_balances: list[ReferenceStockBalance]
