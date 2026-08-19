from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base, uuid_column


class BusinessMembership(Base):
    __tablename__ = "business_memberships"

    id = uuid_column(primary_key=True)
    business_id = Column(UUID_Type(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID_Type(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(UUID_Type(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    status = Column(String(30), default="active", nullable=False)
    invited_at = Column(DateTime(timezone=True))
    joined_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    business = relationship("Business", back_populates="memberships")
    user = relationship("User", back_populates="memberships")
    role = relationship("Role", back_populates="memberships")
