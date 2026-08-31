from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator


class BusinessCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class BusinessProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    industry: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    currency_code: str = Field(min_length=3, max_length=3)
    timezone: str = Field(max_length=100)
    complete_onboarding: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("name", "industry", "phone", "address")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None

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
