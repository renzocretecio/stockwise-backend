from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class MemberInviteRequest(BaseModel):
    email: EmailStr
    role_id: UUID

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class MemberUpdateRequest(BaseModel):
    role_id: UUID | None = None
    status: str | None = Field(default=None, pattern="^(active|suspended)$")


class CustomRoleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    permission_keys: list[str] = Field(min_length=1)

    @field_validator("name", "description")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class InvitationAcceptRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_system_role: bool
    permissions: list[str]
    assignable: bool


class MemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    first_name: str
    last_name: str | None
    role_id: UUID
    role: str
    status: str
    joined_at: datetime | None
    is_current_user: bool


class InvitationResponse(BaseModel):
    id: UUID
    email: str
    role_id: UUID
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
