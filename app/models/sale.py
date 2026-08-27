from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type
from app.models.base import Base, uuid_column

class Sale(Base):
    __tablename__ = "sales"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    reference_number = Column(String(100))
    status = Column(String(30), default='completed', nullable=False)
    sale_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    subtotal = Column(Numeric(14, 2), default=0, nullable=False)
    tax_amount = Column(Numeric(14, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(14, 2), default=0, nullable=False)
    total_amount = Column(Numeric(14, 2), default=0, nullable=False)
    payment_method = Column(String(30))
    notes = Column(Text)
    created_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    voided_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    voided_at = Column(DateTime(timezone=True))
    void_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
    returns = relationship("SaleReturn", back_populates="sale", cascade="all, delete-orphan")
    created_by_user = relationship("User", foreign_keys=[created_by])
    voided_by_user = relationship("User", foreign_keys=[voided_by])

class SaleItem(Base):
    __tablename__ = "sale_items"
    
    id = uuid_column(primary_key=True)
    sale_id = Column(UUID_Type(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    unit_cost = Column(Numeric(14, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(14, 2), default=0, nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    sale = relationship("Sale", back_populates="items")
    product = relationship("Product")
    return_items = relationship("SaleReturnItem", back_populates="sale_item")


class SaleReturn(Base):
    __tablename__ = "sale_returns"
    __table_args__ = (
        CheckConstraint("status IN ('completed', 'cancelled')", name="ck_sale_returns_status"),
        Index("ix_sale_returns_sale_id", "sale_id"),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    sale_id = Column(UUID_Type(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(30), default="completed", nullable=False)
    reason = Column(String(500), nullable=False)
    notes = Column(Text)
    refund_amount = Column(Numeric(14, 2), default=0, nullable=False)
    created_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sale = relationship("Sale", back_populates="returns")
    items = relationship("SaleReturnItem", back_populates="sale_return", cascade="all, delete-orphan")
    created_by_user = relationship("User")


class SaleReturnItem(Base):
    __tablename__ = "sale_return_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_return_items_quantity_positive"),
        UniqueConstraint("return_id", "sale_item_id", name="uq_sale_return_item"),
        Index("ix_sale_return_items_sale_item_id", "sale_item_id"),
    )

    id = uuid_column(primary_key=True)
    return_id = Column(UUID_Type(as_uuid=True), ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False)
    sale_item_id = Column(UUID_Type(as_uuid=True), ForeignKey("sale_items.id", ondelete="RESTRICT"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    unit_cost = Column(Numeric(14, 2), default=0, nullable=False)
    refund_amount = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    sale_return = relationship("SaleReturn", back_populates="items")
    sale_item = relationship("SaleItem", back_populates="return_items")
    product = relationship("Product")
