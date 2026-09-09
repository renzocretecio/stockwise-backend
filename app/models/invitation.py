from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.orm import relationship
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base, uuid_column


class BusinessInvitation(Base):
    __tablename__ = "business_invitations"

    id = uuid_column(primary_key=True)
    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String(255), nullable=False, index=True)
    role_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    invited_by = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(30), nullable=False, default="pending")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    business = relationship("Business")
    role = relationship("Role")
    inviter = relationship("User")
