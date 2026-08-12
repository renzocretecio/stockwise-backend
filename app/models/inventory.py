from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Boolean, Date, Integer, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type
from app.models.base import Base, uuid_column

class StockBalance(Base):
    __tablename__ = "stock_balances"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, unique=True)
    quantity = Column(Numeric(14, 3), default=0, nullable=False)
    reserved_quantity = Column(Numeric(14, 3), default=0, nullable=False)
    average_cost = Column(Numeric(14, 2), default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business")
    product = relationship("Product", back_populates="stock_balance")

class StockMovement(Base):
    __tablename__ = "stock_movements"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    movement_type = Column(String(30), nullable=False)  # purchase, sale, return, adjustment, damage, expired, transfer_in, transfer_out
    quantity = Column(Numeric(14, 3), nullable=False)
    unit_cost = Column(Numeric(14, 2))
    reference_type = Column(String(50))  # purchase, sale, inventory_count, etc
    reference_id = Column(UUID_Type(as_uuid=True))
    reason = Column(String(100))
    notes = Column(Text)
    created_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    business = relationship("Business")
    product = relationship("Product")
    created_by_user = relationship("User")

class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(30), default='draft', nullable=False)  # draft, in_progress, finalized, cancelled
    count_date = Column(Date, server_default=func.current_date(), nullable=False)
    notes = Column(Text)
    created_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    finalized_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    finalized_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business")
    items = relationship("InventoryCountItem", back_populates="inventory_count", cascade="all, delete-orphan")
    created_by_user = relationship("User", foreign_keys=[created_by])
    finalized_by_user = relationship("User", foreign_keys=[finalized_by])

class InventoryCountItem(Base):
    __tablename__ = "inventory_count_items"
    
    id = uuid_column(primary_key=True)
    inventory_count_id = Column(UUID_Type(as_uuid=True), ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    expected_quantity = Column(Numeric(14, 3), default=0, nullable=False)
    counted_quantity = Column(Numeric(14, 3))
    notes = Column(Text)
    counted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    inventory_count = relationship("InventoryCount", back_populates="items")
    product = relationship("Product")