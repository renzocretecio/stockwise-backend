from pydantic import BaseModel, Field
from typing import Optional


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class CategoryItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None
    product_count: int = 0

    class Config:
        from_attributes = True


class CategoriesResponse(BaseModel):
    success: bool = True
    categories: list[CategoryItem]
    pagination: PaginationMeta


class CategoryCreateResponse(BaseModel):
    success: bool = True
    category_id: str
    message: str