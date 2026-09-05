from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class SignUpWithBusinessRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    business_name: str = Field(min_length=1, max_length=150)
    business_slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    currency_code: str = Field(default="PHP", min_length=3, max_length=3)
    timezone: str = Field(default="Asia/Manila", max_length=100)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("first_name", "last_name", "business_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value else value

    @field_validator("business_slug", mode="before")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else None

    @field_validator("currency_code", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown timezone") from exc
        return value

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New passwords do not match")
        if self.current_password == self.new_password:
            raise ValueError("New password must be different")
        return self


class UserProfileUpdate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)

    @field_validator("first_name", "last_name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value else None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    
    class Config:
        from_attributes = True

class BusinessResponse(BaseModel):
    id: str
    name: str
    slug: str
    
    class Config:
        from_attributes = True
