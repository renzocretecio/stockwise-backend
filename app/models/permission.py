from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey
from sqlalchemy.types import UUID as UUID_Type
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        sa_column_kwargs={"server_default": "gen_random_uuid()"},
    )
    key: str = Field(index=True, unique=True, max_length=100)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: UUID = Field(
        foreign_key="roles.id",
        primary_key=True,
    )
    permission_id: UUID = Field(
        foreign_key="permissions.id",
        primary_key=True,
    )