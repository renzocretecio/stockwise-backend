from pydantic import BaseModel, Field, EmailStr
from typing import Optional

class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_previous: bool

class SupplierCreate(BaseModel):
    """Schema for creating a new supplier"""
    name: str = Field(..., min_length=1, max_length=200)
    contact_person: Optional[str] = Field(None, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    lead_time_days: int = Field(default=3, ge=1)
    notes: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "name": "TechSupply Co.",
                "contact_person": "John Doe",
                "email": "contact@techsupply.com",
                "phone": "+63 912 345 6789",
                "address": "123 Business St, Manila",
                "payment_terms": "Net 30",
                "lead_time_days": 5,
                "notes": "Preferred supplier for electronics",
            }
        }


class SupplierUpdate(BaseModel):
    """Schema for updating a supplier"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    contact_person: Optional[str] = Field(None, max_length=200)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    payment_terms: Optional[str] = Field(None, max_length=100)
    lead_time_days: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None


class SupplierResponse(BaseModel):
    """Supplier response"""
    id: str
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    lead_time_days: int
    notes: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class SupplierListItem(BaseModel):
    """Lightweight supplier for list views"""
    id: str
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    lead_time_days: int

    class Config:
        from_attributes = True


class SuppliersResponse(BaseModel):
    success: bool = True
    suppliers: list[SupplierResponse]
    pagination: PaginationMeta


class SupplierCreateResponse(BaseModel):
    """Supplier creation response"""
    success: bool = True
    supplier_id: str
    message: str


class SupplierUpdateResponse(BaseModel):
    """Supplier update response"""
    success: bool = True
    supplier: SupplierResponse
    message: str


class SupplierDeleteResponse(BaseModel):
    """Supplier deletion response"""
    success: bool = True
    message: str