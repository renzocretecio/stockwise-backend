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
    x_business_id: UUID = Header(alias="X-Business-ID"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> RequestContext:
    membership = (
        session.execute(
            select(BusinessMembership).where(
                BusinessMembership.user_id == current_user.id,
                BusinessMembership.business_id == x_business_id,
                BusinessMembership.status == "active",
            )
        )
        .scalars()
        .first()
    )

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not belong to this business",
        )

    from app.services.entitlements import EntitlementService

    EntitlementService.require_membership_access(membership, session)

    return RequestContext(
        user=current_user,
        business_id=x_business_id,
        membership=membership,
    )


def require_permission(permission_key: str):
    def dependency(
        context: RequestContext = Depends(get_request_context),
        session: Session = Depends(get_db),
    ) -> RequestContext:
        if not has_permission(context, permission_key, session):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )

        return context

    return dependency


def has_permission(
    context: RequestContext,
    permission_key: str,
    session: Session,
) -> bool:
    """Return whether the active membership grants a permission."""
    role = context.membership.role
    if (
        role
        and getattr(role, "is_system_role", False)
        and role.name.lower() == "owner"
    ):
        return True

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

    return session.execute(statement).scalar() is not None
