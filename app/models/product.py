from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text, Integer, Numeric, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type
from app.models.base import Base, uuid_column

class Supplier(Base):
    __tablename__ = "suppliers"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    contact_person = Column(String(150))
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    payment_terms = Column(String(100))
    lead_time_days = Column(Integer, default=3, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business")
    products = relationship("Product", back_populates="supplier")
    purchases = relationship("Purchase", back_populates="supplier")

class Product(Base):
    __tablename__ = "products"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    supplier_id = Column(UUID_Type(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"))
    category_id = Column(UUID_Type(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    sku = Column(String(100))
    barcode = Column(String(100))
    name = Column(String(200), nullable=False)
    normalized_name = Column(String(200), nullable=False)
    description = Column(Text)
    brand = Column(String(100))
    unit = Column(String(50), default='unit', nullable=False)
    cost_price = Column(Numeric(14, 2), default=0, nullable=False)
    selling_price = Column(Numeric(14, 2), default=0, nullable=False)
    reorder_point = Column(Numeric(14, 3), default=0, nullable=False)
    safety_stock = Column(Numeric(14, 3), default=0, nullable=False)
    lead_time_days = Column(Integer, default=3, nullable=False)
    is_perishable = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    business = relationship("Business", back_populates="products")
    supplier = relationship("Supplier", back_populates="products")
    category = relationship("Category", back_populates="products")  # ← This stays, it's the real FK relationship

    stock_balance = relationship(
        "StockBalance",
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
    )
    stock_movements = relationship("StockMovement", back_populates="product")
    purchase_items = relationship("PurchaseItem", back_populates="product")
    sale_items = relationship("SaleItem", back_populates="product")
    inventory_count_items = relationship("InventoryCountItem", back_populates="product")