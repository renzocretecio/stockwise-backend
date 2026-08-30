from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base, uuid_column


class InventoryBriefing(Base):
    __tablename__ = "inventory_briefings"
    __table_args__ = (
        UniqueConstraint("business_id", "briefing_date", name="uq_inventory_briefing_business_date"),
        Index("ix_inventory_briefings_business_date", "business_id", "briefing_date"),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    briefing_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="generated")
    headline = Column(String(200), nullable=False)
    summary = Column(JSON, nullable=False, default=list)
    narrator_provider = Column(String(30), nullable=False, default="template")
    narrator_model = Column(String(100))
    metrics_version = Column(String(30), nullable=False, default="v1")
    error_message = Column(Text)
    generated_by = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    recommendations = relationship("InventoryRecommendation", back_populates="briefing", cascade="all, delete-orphan")


class InventoryRecommendation(Base):
    __tablename__ = "inventory_recommendations"
    __table_args__ = (Index("ix_inventory_recommendations_briefing_priority", "briefing_id", "priority_score"),)

    id = uuid_column(primary_key=True)
    briefing_id = Column(UUID_Type(as_uuid=True), ForeignKey("inventory_briefings.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID_Type(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"))
    purchase_id = Column(UUID_Type(as_uuid=True), ForeignKey("purchases.id", ondelete="SET NULL"))
    recommendation_type = Column(String(50), nullable=False)
    priority = Column(String(20), nullable=False)
    priority_score = Column(Integer, nullable=False)
    confidence = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    recommended_action = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=False, default=list)
    metrics = Column(JSON, nullable=False, default=dict)
    rule_id = Column(String(50), nullable=False)
    dismissed_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    briefing = relationship("InventoryBriefing", back_populates="recommendations")
