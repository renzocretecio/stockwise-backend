from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type
from app.models.base import Base, uuid_column

class Business(Base):
    __tablename__ = "businesses"
    
    id = uuid_column(primary_key=True)
    name = Column(String(150), nullable=False)
    slug = Column(String(150), unique=True, nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    address = Column(Text)
    currency_code = Column(String(3), default='PHP', nullable=False)
    timezone = Column(String(100), default='Asia/Manila', nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    memberships = relationship("BusinessMembership", back_populates="business", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="business", cascade="all, delete-orphan")
    suppliers = relationship("Supplier", back_populates="business", cascade="all, delete-orphan")
    purchases = relationship("Purchase", back_populates="business", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="business", cascade="all, delete-orphan")
    stock_balances = relationship("StockBalance", back_populates="business", cascade="all, delete-orphan")
    stock_movements = relationship("StockMovement", back_populates="business", cascade="all, delete-orphan")
    inventory_counts = relationship("InventoryCount", back_populates="business", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="business")
    categories = relationship(
        "Category",
        back_populates="business",
        cascade="all, delete-orphan",
    )

class Role(Base):
    __tablename__ = "roles"
    
    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"))
    name = Column(String(50), nullable=False)
    description = Column(Text)
    is_system_role = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    memberships = relationship("BusinessMembership", back_populates="role")