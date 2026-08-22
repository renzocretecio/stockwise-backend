from pydantic import BaseModel, Field, field_validator
from typing import Optional
from decimal import Decimal

class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool

# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class ProductCreate(BaseModel):
    """Schema for creating a new product"""
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Product name (required)"
    )
    sku: Optional[str] = Field(
        None,
        max_length=100,
        description="Stock Keeping Unit (must be unique per business)"
    )
    barcode: Optional[str] = Field(
        None,
        max_length=100,
        description="Product barcode (must be unique per business)"
    )
    description: Optional[str] = Field(
        None,
        description="Product description"
    )
    category_id: Optional[str] = Field(
        None,
        description="Product Category (must exist)"
    )
    brand: Optional[str] = Field(
        None,
        max_length=100,
        description="Product brand"
    )
    supplier_id: Optional[str] = Field(
        None,
        description="Supplier ID (must exist)"
    )
    unit: str = Field(
        default="unit",
        max_length=50,
        description="Unit of measurement (piece, box, liter, kg, etc.)"
    )
    cost_price: Decimal = Field(
        ...,
        ge=Decimal("0.01"),
        decimal_places=2,
        description="Cost price (must be > 0)"
    )
    selling_price: Decimal = Field(
        ...,
        ge=Decimal("0.01"),
        decimal_places=2,
        description="Selling price (must be > 0)"
    )
    reorder_point: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        decimal_places=3,
        description="Reorder point quantity"
    )
    safety_stock: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        decimal_places=3,
        description="Safety stock level"
    )
    lead_time_days: int = Field(
        default=3,
        ge=1,
        description="Supplier lead time in days"
    )
    is_perishable: bool = Field(
        default=False,
        description="Whether product is perishable"
    )
    
    @field_validator("selling_price")
    @classmethod
    def validate_selling_price(cls, v: Decimal, info) -> Decimal:
        """Ensure selling price >= cost price"""
        if "cost_price" in info.data and v < info.data["cost_price"]:
            raise ValueError("Selling price must be >= cost price")
        return v
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "name": "Laptop Dell XPS 15",
                "sku": "SKU001",
                "barcode": "LP-001",
                "category": "Electronics",
                "brand": "Dell",
                "supplier_id": "supplier-123",
                "unit": "piece",
                "cost_price": "50000.00",
                "selling_price": "75000.00",
                "reorder_point": "10",
                "safety_stock": "5",
                "lead_time_days": 5,
                "is_perishable": False,
            }
        }


class ProductUpdate(BaseModel):
    """Schema for updating a product"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category_id: Optional[str] = Field(None, max_length=100)
    brand: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=50)
    cost_price: Optional[Decimal] = Field(None, ge=Decimal("0.01"), decimal_places=2)
    selling_price: Optional[Decimal] = Field(None, ge=Decimal("0.01"), decimal_places=2)
    reorder_point: Optional[Decimal] = Field(None, ge=Decimal("0"), decimal_places=3)
    safety_stock: Optional[Decimal] = Field(None, ge=Decimal("0"), decimal_places=3)
    lead_time_days: Optional[int] = Field(None, ge=1)
    is_perishable: Optional[bool] = None
    
    class Config:
        from_attributes = True


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ProductResponse(BaseModel):
    id: str
    business_id: str
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    name: str
    normalized_name: str
    description: Optional[str] = None
    brand: Optional[str] = None
    unit: str
    quantity: float
    stock_status: str
    cost_price: float
    selling_price: float
    reorder_point: float
    safety_stock: float
    lead_time_days: int
    is_perishable: bool
    is_active: bool
    margin_percent: float = Field(description="Profit margin as percentage")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class ProductListItem(BaseModel):
    """Lightweight product for list views"""
    id: str
    name: str
    sku: Optional[str] = None
    category: Optional[str] = None
    unit: str
    cost_price: float
    selling_price: float
    is_perishable: bool
    margin_percent: float
    
    class Config:
        from_attributes = True


class ProductsResponse(BaseModel):
    """List products response"""
    success: bool = True
    products: list[ProductResponse]
    pagination: PaginationMeta


class ProductCreateResponse(BaseModel):
    """Product creation response"""
    success: bool = True
    product_id: str
    message: str


class ProductUpdateResponse(BaseModel):
    """Product update response"""
    success: bool = True
    product: ProductResponse
    message: str


class ProductDeleteResponse(BaseModel):
    """Product deletion response"""
    success: bool = True
    message: str


class ProductOverallStatus(BaseModel):
    total_products: int
    in_stock: int
    low_stock: int
    out_of_stock: int

# ============================================================================
# CATEGORY SCHEMAS
# ============================================================================

class CategoryCreate(BaseModel):
    """Schema for creating a category"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


class CategoryItem(BaseModel):
    """Category response"""
    id: str
    business_id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    
    class Config:
        from_attributes = True


class CategoriesResponse(BaseModel):
    """List categories response"""
    success: bool = True
    categories: list[CategoryItem]
    total: int = Field(default=0, description="Total category count")


# ============================================================================
# ERROR SCHEMAS
# ============================================================================

class ErrorResponse(BaseModel):
    """Error response"""
    success: bool = False
    error: str
    detail: Optional[str] = None