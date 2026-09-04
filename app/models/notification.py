from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base, uuid_column


class WeeklyOwnerSummarySettings(Base):
    __tablename__ = "weekly_owner_summary_settings"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            name="uq_weekly_owner_summary_business",
        ),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    send_weekday = Column(Integer, nullable=False, default=0)
    send_hour = Column(Integer, nullable=False, default=7)
    send_minute = Column(Integer, nullable=False, default=0)
    recipients = Column(JSON, nullable=False, default=list)
    included_sections = Column(JSON, nullable=False, default=list)
    action_required_only = Column(Boolean, nullable=False, default=False)
    last_sent_period_end = Column(String(10))

    business = relationship("Business")