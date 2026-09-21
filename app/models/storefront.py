import secrets

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base, uuid_column


class PublicStore(Base):
    __tablename__ = "public_stores"
    __table_args__ = (
        CheckConstraint(
            "out_of_stock_behavior IN " "('mark_sold_out', 'hide', 'continue_selling')",
            name="ck_public_stores_stock_behavior",
        ),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    slug = Column(String(150), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    logo_url = Column(Text)
    banner_url = Column(Text)
    is_active = Column(Boolean, default=False, nullable=False)
    out_of_stock_behavior = Column(
        String(30),
        default="mark_sold_out",
        nullable=False,
    )
    pickup_enabled = Column(Boolean, default=True, nullable=False)
    delivery_enabled = Column(Boolean, default=True, nullable=False)
    payment_methods = Column(JSON, default=list, nullable=False)
    payment_instructions = Column(JSON, default=dict, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    business = relationship("Business", back_populates="public_store")
    products = relationship(
        "StoreProduct",
        back_populates="store",
        cascade="all, delete-orphan",
    )
    orders = relationship(
        "StoreOrder",
        back_populates="store",
        cascade="all, delete-orphan",
    )


class StoreProduct(Base):
    __tablename__ = "store_products"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "product_id",
            name="uq_store_products_store_product",
        ),
        CheckConstraint(
            "public_price >= 0",
            name="ck_store_products_public_price",
        ),
    )

    id = uuid_column(primary_key=True)
    store_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("public_stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_public = Column(Boolean, default=False, nullable=False)
    public_name = Column(String(200))
    public_description = Column(Text)
    public_price = Column(Numeric(14, 2), nullable=False)
    public_image_url = Column(Text)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    store = relationship("PublicStore", back_populates="products")
    product = relationship("Product", back_populates="store_listing")


class StoreOrder(Base):
    __tablename__ = "store_orders"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "reference_number",
            name="uq_store_orders_business_reference",
        ),
        CheckConstraint(
            "status IN "
            "('new', 'confirmed', 'processing', 'ready', 'shipped', "
            "'completed', 'cancelled')",
            name="ck_store_orders_status",
        ),
        CheckConstraint(
            "delivery_method IN ('pickup', 'delivery')",
            name="ck_store_orders_delivery_method",
        ),
        Index(
            "ix_store_orders_business_status_created",
            "business_id",
            "status",
            "created_at",
        ),
    )

    id = uuid_column(primary_key=True)
    store_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("public_stores.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sale_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("sales.id", ondelete="SET NULL"),
        unique=True,
    )
    reference_number = Column(String(100), nullable=False)
    tracking_token = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    status = Column(String(30), default="new", nullable=False)
    customer_name = Column(String(150), nullable=False)
    customer_contact = Column(String(100), nullable=False)
    delivery_method = Column(String(20), nullable=False)
    delivery_address = Column(Text)
    customer_notes = Column(Text)
    payment_method = Column(String(30), nullable=False)
    subtotal = Column(Numeric(14, 2), default=0, nullable=False)
    total_amount = Column(Numeric(14, 2), default=0, nullable=False)
    confirmed_by = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    completed_by = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    cancelled_by = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    confirmed_at = Column(DateTime(timezone=True))
    processing_at = Column(DateTime(timezone=True))
    ready_at = Column(DateTime(timezone=True))
    shipped_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    cancellation_reason = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    store = relationship("PublicStore", back_populates="orders")
    business = relationship("Business")
    sale = relationship("Sale")
    items = relationship(
        "StoreOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class StoreOrderItem(Base):
    __tablename__ = "store_order_items"
    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "product_id",
            name="uq_store_order_items_order_product",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_store_order_items_quantity",
        ),
        CheckConstraint(
            "reserved_quantity >= 0 AND reserved_quantity <= quantity",
            name="ck_store_order_items_reserved_quantity",
        ),
    )

    id = uuid_column(primary_key=True)
    order_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("store_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_name = Column(String(200), nullable=False)
    sku = Column(String(100))
    quantity = Column(Numeric(14, 3), nullable=False)
    reserved_quantity = Column(Numeric(14, 3), default=0, nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    unit_cost = Column(Numeric(14, 2), default=0, nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    order = relationship("StoreOrder", back_populates="items")
    product = relationship("Product")
