from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from typing import Optional


class ImportRowError(BaseModel):
    row_number: int
    message: str


class ProductImportRow(BaseModel):
    row_number: int
    sku: Optional[str] = None
    barcode: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    unit: str = "unit"
    cost_price: float | str  # Accept float or string
    selling_price: float | str
    reorder_point: float | str = "0"
    safety_stock: float | str = "0"
    lead_time_days: int = 3
    is_perishable: bool = False
    supplier_name: Optional[str] = None
    
    # Convert to Decimal when accessing
    def get_cost_price(self) -> Decimal:
        return Decimal(str(self.cost_price))
    
    def get_selling_price(self) -> Decimal:
        return Decimal(str(self.selling_price))
    
    def get_reorder_point(self) -> Decimal:
        return Decimal(str(self.reorder_point))
    
    def get_safety_stock(self) -> Decimal:
        return Decimal(str(self.safety_stock))


class ProductImportPreview(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ProductImportRow]
    errors: list[ImportRowError]


class ProductImportCommitRequest(BaseModel):
    rows: list[ProductImportRow]