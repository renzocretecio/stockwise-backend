from sqlalchemy import Column, DateTime, Index, JSON, String, UniqueConstraint, func
from sqlalchemy import UUID as UUID_Type

from app.models.base import Base, uuid_column


class SyncEvent(Base):
    __tablename__ = "sync_events"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "client_event_id",
            name="uq_sync_events_business_client_event",
        ),
        Index("ix_sync_events_business_created_at", "business_id", "created_at"),
    )

    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), nullable=False)
    user_id = Column(UUID_Type(as_uuid=True), nullable=False)
    client_event_id = Column(String(255), nullable=False)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSON, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )