from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.models.auth import User
from app.models.membership import BusinessMembership
from app.models.permission import Permission, RolePermission
from app.core.security import get_current_user


@dataclass
class RequestContext:
    user: User
    business_id: UUID
    membership: BusinessMembership


def get_request_context(
    business_id: UUID = Header(alias="X-Business-ID"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> RequestContext:
    membership = session.execute(
        select(BusinessMembership).where(
            BusinessMembership.user_id == current_user.id,
            BusinessMembership.business_id == business_id,
            BusinessMembership.status == "active",
        )
    ).scalars().first()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not belong to this business",
        )

    return RequestContext(
        user=current_user,
        business_id=business_id,
        membership=membership,
    )


def require_permission(permission_key: str):
    def dependency(
        context: RequestContext = Depends(get_request_context),
        session: Session = Depends(get_db),
    ) -> RequestContext:
        role = context.membership.role
        if (
            role
            and getattr(role, "is_system_role", False)
            and role.name.lower() == "owner"
        ):
            return context

        statement = (
            select(Permission.id)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id,
            )
            .where(
                RolePermission.role_id == context.membership.role_id,
                Permission.key == permission_key,
            )
        )

        permission_exists = session.execute(statement).scalar()

        if not permission_exists:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )

        return context

    return dependency
