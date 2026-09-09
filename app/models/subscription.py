from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base, uuid_column


class BusinessSubscription(Base):
    __tablename__ = "business_subscriptions"
    __table_args__ = (
        UniqueConstraint("business_id", name="uq_business_subscriptions_business"),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan = Column(String(32), nullable=False, default="free")
    status = Column(String(32), nullable=False, default="active")
    provider = Column(String(32), nullable=False, default="manual")
    provider_customer_id = Column(String(255))
    provider_subscription_id = Column(String(255), unique=True)
    additional_member_seats = Column(Integer, nullable=False, default=0)
    current_period_ends_at = Column(DateTime(timezone=True))
    trial_started_at = Column(DateTime(timezone=True))
    trial_ends_at = Column(DateTime(timezone=True))
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    cancelled_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    business = relationship("Business", back_populates="subscription")


class SubscriptionUsage(Base):
    __tablename__ = "subscription_usage"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "metric",
            "period_start",
            name="uq_subscription_usage_business_metric_period",
        ),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric = Column(String(64), nullable=False)
    period_start = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
