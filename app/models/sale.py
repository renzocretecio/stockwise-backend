from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, func
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")
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