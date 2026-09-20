import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id = Column(
        UUID_Type(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    key = Column(String(100), index=True, unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
