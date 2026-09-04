from sqlalchemy import Column, String, DateTime, ForeignKey, Date, Numeric, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type
from app.models.base import Base, uuid_column

class Purchase(Base):
    __tablename__ = "purchases"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    supplier_id = Column(UUID_Type(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"))
    reference_number = Column(String(100))
    status = Column(String(30), default='draft', nullable=False)
    purchase_date = Column(Date, server_default=func.current_date(), nullable=False)
    expected_delivery_date = Column(Date, index=True)
    ordered_at = Column(DateTime(timezone=True))
    received_at = Column(DateTime(timezone=True))
    subtotal = Column(Numeric(14, 2), default=0, nullable=False)
    tax_amount = Column(Numeric(14, 2), default=0, nullable=False)
    discount_amount = Column(Numeric(14, 2), default=0, nullable=False)
    total_amount = Column(Numeric(14, 2), default=0, nullable=False)
    notes = Column(Text)
    created_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    ordered_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    received_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business")
    supplier = relationship("Supplier", back_populates="purchases")
    items = relationship("PurchaseItem", back_populates="purchase", cascade="all, delete-orphan")
    created_by_user = relationship("User", foreign_keys=[created_by])
    ordered_by_user = relationship("User", foreign_keys=[ordered_by])
    received_by_user = relationship("User", foreign_keys=[received_by])

class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    
    id = uuid_column(primary_key=True)
    purchase_id = Column(UUID_Type(as_uuid=True), ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False)
    unit_cost = Column(Numeric(14, 2), nullable=False)
    line_total = Column(Numeric(14, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    purchase = relationship("Purchase", back_populates="items")
    product = relationship("Product")
