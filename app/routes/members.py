from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.permissions import (
    RequestContext,
    get_request_context,
    require_permission,
)
from app.config.rbac import PERMISSIONS
from app.core.security import get_current_user
from app.models import Role, User
from app.schemas.members import (
    CustomRoleRequest,
    InvitationAcceptRequest,
    MemberInviteRequest,
    MemberUpdateRequest,
)
from app.services.entitlements import EntitlementService
from app.services.members import MemberService


router = APIRouter(tags=["members"])


@router.get("/members")
def list_members(
    context: RequestContext = Depends(require_permission("members.read")),
    db: Session = Depends(get_db),
):
    return {
        "members": MemberService.list_members(
            context.business_id,
            context.user.id,
            db,
        ),
        "invitations": MemberService.list_invitations(
            context.business_id,
            db,
        ),
        "roles": MemberService.list_roles(context.business_id, db),
        "subscription": EntitlementService.usage_summary(
            str(context.business_id),
            db,
            user_id=str(context.user.id),
        ),
    }


@router.get("/members/roles")
def list_roles(
    context: RequestContext = Depends(require_permission("members.read")),
    db: Session = Depends(get_db),
):
    return {"roles": MemberService.list_roles(context.business_id, db)}


@router.get("/members/permissions")
def list_permissions(
    _: RequestContext = Depends(require_permission("members.update_role")),
):
    return {
        "permissions": [
            {"key": key, "description": description}
            for key, description in PERMISSIONS.items()
            if key not in {"billing.manage", "business.update"}
        ]
    }


@router.post("/members/invitations", status_code=status.HTTP_201_CREATED)
def invite_member(
    payload: MemberInviteRequest,
    background_tasks: BackgroundTasks,
    context: RequestContext = Depends(require_permission("members.invite")),
    db: Session = Depends(get_db),
):
    invitation, token = MemberService.create_invitation(
        context.business_id,
        str(payload.email),
        payload.role_id,
        context.user.id,
        db,
    )
    role = (
        db.query(Role)
        .filter(
            Role.id == invitation.role_id,
        )
        .first()
    )
    accept_url = MemberService.invitation_url(token)
    background_tasks.add_task(
        MemberService.send_invitation_email,
        invitation.email,
        context.membership.business.name,
        role.name,
        accept_url,
    )
    return {
        "invitation": {
            "id": invitation.id,
            "email": invitation.email,
            "role_id": invitation.role_id,
            "role": role.name,
            "status": invitation.status,
            "expires_at": invitation.expires_at,
            "created_at": invitation.created_at,
        },
        # Returned only at creation so local setups without SMTP remain
        # testable. The stored database value is a one-way token hash.
        "accept_url": accept_url,
        "email_delivery": (
            "scheduled" if MemberService.email_is_configured() else "not_configured"
        ),
    }


@router.delete("/members/invitations/{invitation_id}")
def revoke_invitation(
    invitation_id: UUID,
    context: RequestContext = Depends(require_permission("members.invite")),
    db: Session = Depends(get_db),
):
    MemberService.revoke_invitation(
        context.business_id,
        invitation_id,
        context.user.id,
        db,
    )
    return {"success": True}


@router.patch("/members/{membership_id}")
def update_member(
    membership_id: UUID,
    payload: MemberUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    if payload.role_id:
        require_permission("members.update_role")(
            context=context,
            session=db,
        )
    if payload.status:
        require_permission("members.remove")(
            context=context,
            session=db,
        )
    if not payload.role_id and not payload.status:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a role or membership status to update",
        )
    membership = MemberService.update_member(
        context.business_id,
        membership_id,
        context.user.id,
        payload.role_id,
        payload.status,
        db,
    )
    return {
        "success": True,
        "membership_id": membership.id,
        "role_id": membership.role_id,
        "status": membership.status,
    }


@router.delete("/members/{membership_id}")
def remove_member(
    membership_id: UUID,
    context: RequestContext = Depends(require_permission("members.remove")),
    db: Session = Depends(get_db),
):
    MemberService.remove_member(
        context.business_id,
        membership_id,
        context.user.id,
        db,
    )
    return {"success": True}


@router.post("/members/roles", status_code=status.HTTP_201_CREATED)
def create_custom_role(
    payload: CustomRoleRequest,
    context: RequestContext = Depends(require_permission("members.update_role")),
    db: Session = Depends(get_db),
):
    role = MemberService.create_custom_role(
        context.business_id,
        context.user.id,
        payload.name,
        payload.description,
        payload.permission_keys,
        db,
    )
    return {"role_id": role.id, "success": True}


@router.put("/members/roles/{role_id}")
def update_custom_role(
    role_id: UUID,
    payload: CustomRoleRequest,
    context: RequestContext = Depends(require_permission("members.update_role")),
    db: Session = Depends(get_db),
):
    role = MemberService.update_custom_role(
        context.business_id,
        role_id,
        context.user.id,
        payload.name,
        payload.description,
        payload.permission_keys,
        db,
    )
    return {"role_id": role.id, "success": True}


@router.delete("/members/roles/{role_id}")
def delete_custom_role(
    role_id: UUID,
    context: RequestContext = Depends(require_permission("members.update_role")),
    db: Session = Depends(get_db),
):
    MemberService.delete_custom_role(
        context.business_id,
        role_id,
        context.user.id,
        db,
    )
    return {"success": True}


@router.get("/invitations/{token}")
def get_invitation(token: str, db: Session = Depends(get_db)):
    return MemberService.invitation_details(token, db)


@router.post("/invitations/accept")
def accept_invitation(
    payload: InvitationAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = MemberService.accept_invitation(
        payload.token,
        current_user,
        db,
    )
    return {
        "success": True,
        "business_id": membership.business_id,
        "role": membership.role.name,
    }
