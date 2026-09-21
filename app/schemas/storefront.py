from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class OutOfStockBehavior(str, Enum):
    MARK_SOLD_OUT = "mark_sold_out"
    HIDE = "hide"
    CONTINUE_SELLING = "continue_selling"


class StorePaymentMethod(str, Enum):
    COD = "cod"
    GCASH = "gcash"
    BANK_TRANSFER = "bank_transfer"
    PAY_ON_PICKUP = "pay_on_pickup"


class DeliveryMethod(str, Enum):
    PICKUP = "pickup"
    DELIVERY = "delivery"


class StoreOrderStatus(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    READY = "ready"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class StorefrontCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = Field(default=None, max_length=2000)
    logo_url: str | None = Field(default=None, max_length=2000)
    banner_url: str | None = Field(default=None, max_length=2000)
    is_active: bool = False
    out_of_stock_behavior: OutOfStockBehavior = OutOfStockBehavior.MARK_SOLD_OUT
    pickup_enabled: bool = True
    delivery_enabled: bool = True
    payment_methods: list[StorePaymentMethod] = Field(
        default_factory=lambda: [StorePaymentMethod.COD]
    )
    payment_instructions: dict[str, str] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("slug", mode="before")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("payment_methods")
    @classmethod
    def unique_payment_methods(
        cls,
        value: list[StorePaymentMethod],
    ) -> list[StorePaymentMethod]:
        if not value:
            raise ValueError("At least one payment method is required")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_fulfillment(self):
        if not self.pickup_enabled and not self.delivery_enabled:
            raise ValueError("Enable pickup, delivery, or both")
        return self


class StorefrontUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    logo_url: str | None = Field(default=None, max_length=2000)
    banner_url: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    out_of_stock_behavior: OutOfStockBehavior | None = None
    pickup_enabled: bool | None = None
    delivery_enabled: bool | None = None
    payment_methods: list[StorePaymentMethod] | None = None
    payment_instructions: dict[str, str] | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("payment_methods")
    @classmethod
    def unique_payment_methods(
        cls,
        value: list[StorePaymentMethod] | None,
    ) -> list[StorePaymentMethod] | None:
        if value is not None and not value:
            raise ValueError("At least one payment method is required")
        return list(dict.fromkeys(value)) if value is not None else None


class StoreProductUpdate(BaseModel):
    is_public: bool = True
    public_name: str | None = Field(default=None, max_length=200)
    public_description: str | None = Field(default=None, max_length=4000)
    public_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        decimal_places=2,
    )
    public_image_url: str | None = Field(default=None, max_length=2000)
    sort_order: int = Field(default=0, ge=0)


class StoreProductBulkPublish(BaseModel):
    product_ids: list[UUID] = Field(..., min_length=1, max_length=100)
    is_public: bool

    @field_validator("product_ids")
    @classmethod
    def unique_product_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Duplicate product IDs are not allowed")
        return value


class PublicOrderItemCreate(BaseModel):
    store_product_id: UUID
    quantity: Decimal = Field(..., gt=0, decimal_places=3)


class PublicOrderCreate(BaseModel):
    items: list[PublicOrderItemCreate] = Field(..., min_length=1, max_length=100)
    customer_name: str = Field(..., min_length=1, max_length=150)
    customer_contact: str = Field(..., min_length=3, max_length=100)
    delivery_method: DeliveryMethod
    delivery_address: str | None = Field(default=None, max_length=2000)
    customer_notes: str | None = Field(default=None, max_length=2000)
    payment_method: StorePaymentMethod

    @field_validator("customer_name", "customer_contact", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("items")
    @classmethod
    def unique_products(
        cls,
        value: list[PublicOrderItemCreate],
    ) -> list[PublicOrderItemCreate]:
        ids = [item.store_product_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate store_product_id in order items")
        return value

    @model_validator(mode="after")
    def delivery_requires_address(self):
        if (
            self.delivery_method == DeliveryMethod.DELIVERY
            and not (self.delivery_address or "").strip()
        ):
            raise ValueError("Delivery address is required for delivery orders")
        return self


class StoreOrderStatusUpdate(BaseModel):
    status: StoreOrderStatus
    cancellation_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def cancellation_requires_reason(self):
        if (
            self.status == StoreOrderStatus.CANCELLED
            and not (self.cancellation_reason or "").strip()
        ):
            raise ValueError("Cancellation reason is required")
        return self
