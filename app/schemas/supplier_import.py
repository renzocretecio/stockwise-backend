from pydantic import BaseModel, EmailStr, Field


class SupplierImportRowError(BaseModel):
    row_number: int
    message: str


class SupplierImportRow(BaseModel):
    row_number: int
    name: str = Field(min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    payment_terms: str | None = Field(default=None, max_length=100)
    lead_time_days: int = Field(default=3, ge=1)
    notes: str | None = None


class SupplierImportPreview(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[SupplierImportRow]
    errors: list[SupplierImportRowError]


class SupplierImportCommitRequest(BaseModel):
    rows: list[SupplierImportRow] = Field(min_length=1)


class SupplierImportCommitError(BaseModel):
    row_number: int
    field: str
    message: str


class SupplierImportCommitResponse(BaseModel):
    created: int
    errors: list[SupplierImportCommitError]
    message: str
