from sqlalchemy import Column, DateTime, Index, Integer, String, Text, UniqueConstraint, func

from app.models.base import Base, uuid_column


class IdempotencyRequest(Base):
    __tablename__ = "idempotency_requests"
    __table_args__ = (
        UniqueConstraint(
            "request_scope",
            "idempotency_key",
            name="uq_idempotency_request_scope_key",
        ),
        Index("ix_idempotency_requests_created_at", "created_at"),
    )

    id = uuid_column(primary_key=True)
    request_scope = Column(String(128), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    response_status = Column(Integer)
    response_body = Column(Text)
    response_content_type = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)