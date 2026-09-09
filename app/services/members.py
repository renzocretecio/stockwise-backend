import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config.rbac import PERMISSIONS
from app.config.settings import settings
from app.models import (
    AuditLog,
    Business,
    BusinessInvitation,
    BusinessMembership,
    Role,
    User,
)
from app.models.permission import Permission, RolePermission
from app.services.entitlements import EntitlementService


INVITATION_LIFETIME_DAYS = 7
OWNER_ONLY_PERMISSIONS = {"billing.manage", "business.update"}


class MemberService:
    @staticmethod
    def email_is_configured() -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_FROM_EMAIL)

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def list_members(
        business_id: UUID,
        current_user_id: UUID,
        db: Session,
    ) -> list[dict]:
        memberships = (
            db.query(BusinessMembership)
            .join(User, User.id == BusinessMembership.user_id)
            .join(Role, Role.id == BusinessMembership.role_id)
            .filter(
                BusinessMembership.business_id == business_id,
                BusinessMembership.status.in_(("active", "suspended")),
            )
            .order_by(User.first_name, User.last_name, User.email)
            .all()
        )
        return [
            {
                "id": membership.id,
                "user_id": membership.user_id,
                "email": membership.user.email,
                "first_name": membership.user.first_name,
                "last_name": membership.user.last_name,
                "role_id": membership.role_id,
                "role": membership.role.name,
                "status": membership.status,
                "joined_at": membership.joined_at,
                "is_current_user": membership.user_id == current_user_id,
            }
            for membership in memberships
        ]

    @staticmethod
    def list_invitations(business_id: UUID, db: Session) -> list[dict]:
        now = datetime.now(timezone.utc)
        invitations = (
            db.query(BusinessInvitation)
            .join(Role, Role.id == BusinessInvitation.role_id)
            .filter(
                BusinessInvitation.business_id == business_id,
                BusinessInvitation.status == "pending",
            )
            .order_by(BusinessInvitation.created_at.desc())
            .all()
        )
        changed = False
        result = []
        for invitation in invitations:
            if MemberService.is_expired(invitation.expires_at, now):
                invitation.status = "expired"
                changed = True
                continue
            result.append(
                {
                    "id": invitation.id,
                    "email": invitation.email,
                    "role_id": invitation.role_id,
                    "role": invitation.role.name,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at,
                    "created_at": invitation.created_at,
                }
            )
        if changed:
            db.commit()
        return result

    @staticmethod
    def list_roles(business_id: UUID, db: Session) -> list[dict]:
        roles = (
            db.query(Role)
            .filter(Role.business_id == business_id)
            .order_by(Role.is_system_role.desc(), Role.name)
            .all()
        )
        result = []
        for role in roles:
            keys = [
                row[0]
                for row in (
                    db.query(Permission.key)
                    .join(
                        RolePermission,
                        RolePermission.permission_id == Permission.id,
                    )
                    .filter(RolePermission.role_id == role.id)
                    .order_by(Permission.key)
                    .all()
                )
            ]
            result.append(
                {
                    "id": role.id,
                    "name": role.name,
                    "description": role.description,
                    "is_system_role": role.is_system_role,
                    "permissions": keys,
                    "assignable": role.name.lower() != "owner",
                }
            )
        return result

    @staticmethod
    def create_invitation(
        business_id: UUID,
        email: str,
        role_id: UUID,
        invited_by: UUID,
        db: Session,
    ) -> tuple[BusinessInvitation, str]:
        db.query(Business).filter(Business.id == business_id).with_for_update().one()
        role = MemberService.require_assignable_role(
            business_id,
            role_id,
            db,
        )
        existing_member = (
            db.query(BusinessMembership)
            .join(User, User.id == BusinessMembership.user_id)
            .filter(
                BusinessMembership.business_id == business_id,
                User.email == email,
                BusinessMembership.status.in_(("active", "suspended")),
            )
            .first()
        )
        if existing_member:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This person is already a member of the business",
            )

        now = datetime.now(timezone.utc)
        invitation = (
            db.query(BusinessInvitation)
            .filter(
                BusinessInvitation.business_id == business_id,
                BusinessInvitation.email == email,
                BusinessInvitation.status == "pending",
            )
            .first()
        )
        is_reserved = bool(
            invitation and not MemberService.is_expired(invitation.expires_at, now)
        )
        if not is_reserved:
            EntitlementService.require_member_capacity(
                str(business_id),
                db,
            )

        token = secrets.token_urlsafe(48)
        if invitation:
            invitation.role_id = role.id
            invitation.invited_by = invited_by
            invitation.token_hash = MemberService.token_hash(token)
            invitation.expires_at = now + timedelta(
                days=INVITATION_LIFETIME_DAYS,
            )
            invitation.status = "pending"
        else:
            invitation = BusinessInvitation(
                business_id=business_id,
                email=email,
                role_id=role.id,
                invited_by=invited_by,
                token_hash=MemberService.token_hash(token),
                expires_at=now + timedelta(days=INVITATION_LIFETIME_DAYS),
                status="pending",
            )
            db.add(invitation)

        db.flush()
        MemberService.add_audit_log(
            db,
            business_id,
            invited_by,
            "member.invited",
            "business_invitation",
            invitation.id,
            {"email": email, "role": role.name},
        )
        db.commit()
        db.refresh(invitation)
        return invitation, token

    @staticmethod
    def invitation_details(token: str, db: Session) -> dict:
        invitation = MemberService.find_valid_invitation(token, db)
        business = (
            db.query(Business)
            .filter(
                Business.id == invitation.business_id,
            )
            .first()
        )
        role = db.query(Role).filter(Role.id == invitation.role_id).first()
        return {
            "business_name": business.name,
            "email": invitation.email,
            "role": role.name,
            "expires_at": invitation.expires_at,
        }

    @staticmethod
    def accept_invitation(
        token: str,
        user: User,
        db: Session,
    ) -> BusinessMembership:
        invitation = MemberService.find_valid_invitation(token, db)
        if invitation.email != user.email.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sign in with the email address that was invited",
            )

        db.query(Business).filter(
            Business.id == invitation.business_id,
        ).with_for_update().one()

        EntitlementService.require_member_capacity(
            str(invitation.business_id),
            db,
            additional_members=0,
        )
        membership = (
            db.query(BusinessMembership)
            .filter(
                BusinessMembership.business_id == invitation.business_id,
                BusinessMembership.user_id == user.id,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        if membership:
            membership.role_id = invitation.role_id
            membership.status = "active"
            membership.joined_at = membership.joined_at or now
        else:
            membership = BusinessMembership(
                business_id=invitation.business_id,
                user_id=user.id,
                role_id=invitation.role_id,
                status="active",
                invited_at=invitation.created_at,
                joined_at=now,
            )
            db.add(membership)

        invitation.status = "accepted"
        invitation.accepted_at = now
        db.flush()
        MemberService.add_audit_log(
            db,
            invitation.business_id,
            user.id,
            "member.invitation_accepted",
            "business_membership",
            membership.id,
            {"role_id": str(invitation.role_id)},
        )
        db.commit()
        db.refresh(membership)
        return membership

    @staticmethod
    def revoke_invitation(
        business_id: UUID,
        invitation_id: UUID,
        actor_id: UUID,
        db: Session,
    ) -> None:
        invitation = (
            db.query(BusinessInvitation)
            .filter(
                BusinessInvitation.id == invitation_id,
                BusinessInvitation.business_id == business_id,
                BusinessInvitation.status == "pending",
            )
            .first()
        )
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")
        invitation.status = "revoked"
        MemberService.add_audit_log(
            db,
            business_id,
            actor_id,
            "member.invitation_revoked",
            "business_invitation",
            invitation.id,
            {"email": invitation.email},
        )
        db.commit()

    @staticmethod
    def update_member(
        business_id: UUID,
        membership_id: UUID,
        actor_id: UUID,
        role_id: UUID | None,
        membership_status: str | None,
        db: Session,
    ) -> BusinessMembership:
        membership = (
            db.query(BusinessMembership)
            .filter(
                BusinessMembership.id == membership_id,
                BusinessMembership.business_id == business_id,
                BusinessMembership.status.in_(("active", "suspended")),
            )
            .first()
        )
        if not membership:
            raise HTTPException(status_code=404, detail="Member not found")
        if membership.role.name.lower() == "owner":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The business owner cannot be changed here",
            )
        if membership.user_id == actor_id and membership_status == "suspended":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot suspend your own membership",
            )

        old_values = {
            "role": membership.role.name,
            "status": membership.status,
        }
        if role_id:
            role = MemberService.require_assignable_role(
                business_id,
                role_id,
                db,
            )
            membership.role_id = role.id
        if membership_status:
            membership.status = membership_status

        db.flush()
        MemberService.add_audit_log(
            db,
            business_id,
            actor_id,
            "member.updated",
            "business_membership",
            membership.id,
            {
                "old": old_values,
                "role_id": str(membership.role_id),
                "status": membership.status,
            },
        )
        db.commit()
        db.refresh(membership)
        return membership

    @staticmethod
    def remove_member(
        business_id: UUID,
        membership_id: UUID,
        actor_id: UUID,
        db: Session,
    ) -> None:
        membership = (
            db.query(BusinessMembership)
            .filter(
                BusinessMembership.id == membership_id,
                BusinessMembership.business_id == business_id,
                BusinessMembership.status.in_(("active", "suspended")),
            )
            .first()
        )
        if not membership:
            raise HTTPException(status_code=404, detail="Member not found")
        if membership.role.name.lower() == "owner":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The business owner cannot be removed",
            )
        if membership.user_id == actor_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot remove your own membership",
            )
        membership.status = "removed"
        MemberService.add_audit_log(
            db,
            business_id,
            actor_id,
            "member.removed",
            "business_membership",
            membership.id,
            {"user_id": str(membership.user_id)},
        )
        db.commit()

    @staticmethod
    def create_custom_role(
        business_id: UUID,
        actor_id: UUID,
        name: str,
        description: str | None,
        permission_keys: list[str],
        db: Session,
    ) -> Role:
        EntitlementService.require_feature(
            str(business_id),
            "custom_roles",
            db,
        )
        MemberService.validate_custom_permissions(permission_keys)
        duplicate = (
            db.query(Role)
            .filter(
                Role.business_id == business_id,
                Role.name.ilike(name),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A role with this name already exists",
            )
        role = Role(
            business_id=business_id,
            name=name,
            description=description,
            is_system_role=False,
        )
        db.add(role)
        db.flush()
        MemberService.replace_role_permissions(role.id, permission_keys, db)
        MemberService.add_audit_log(
            db,
            business_id,
            actor_id,
            "role.created",
            "role",
            role.id,
            {"name": name, "permissions": sorted(permission_keys)},
        )
        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    def update_custom_role(
        business_id: UUID,
        role_id: UUID,
        actor_id: UUID,
        name: str,
        description: str | None,
        permission_keys: list[str],
        db: Session,
    ) -> Role:
        EntitlementService.require_feature(
            str(business_id),
            "custom_roles",
            db,
        )
        role = MemberService.require_custom_role(business_id, role_id, db)
        MemberService.validate_custom_permissions(permission_keys)
        duplicate = (
            db.query(Role)
            .filter(
                Role.business_id == business_id,
                Role.id != role.id,
                Role.name.ilike(name),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A role with this name already exists",
            )
        old_values = {
            "name": role.name,
            "description": role.description,
        }
        role.name = name
        role.description = description
        MemberService.replace_role_permissions(role.id, permission_keys, db)
        MemberService.add_audit_log(
            db,
            business_id,
            actor_id,
            "role.updated",
            "role",
            role.id,
            {
                "old": old_values,
                "name": name,
                "permissions": sorted(permission_keys),
            },
        )
        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    def delete_custom_role(
        business_id: UUID,
        role_id: UUID,
        actor_id: UUID,
        db: Session,
    ) -> None:
        EntitlementService.require_feature(
            str(business_id),
            "custom_roles",
            db,
        )
        role = MemberService.require_custom_role(business_id, role_id, db)
        in_use = (
            db.query(BusinessMembership.id)
            .filter(
                BusinessMembership.role_id == role.id,
                BusinessMembership.status.in_(("active", "suspended")),
            )
            .first()
        )
        if in_use:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reassign members before deleting this role",
            )
        db.query(RolePermission).filter(
            RolePermission.role_id == role.id,
        ).delete(synchronize_session=False)
        MemberService.add_audit_log(
            db,
            business_id,
            actor_id,
            "role.deleted",
            "role",
            role.id,
            {"name": role.name},
        )
        db.delete(role)
        db.commit()

    @staticmethod
    def replace_role_permissions(
        role_id: UUID,
        permission_keys: list[str],
        db: Session,
    ) -> None:
        permissions = (
            db.query(Permission)
            .filter(
                Permission.key.in_(permission_keys),
            )
            .all()
        )
        db.query(RolePermission).filter(
            RolePermission.role_id == role_id,
        ).delete(synchronize_session=False)
        if permissions:
            db.execute(
                RolePermission.__table__.insert(),
                [
                    {"role_id": role_id, "permission_id": permission.id}
                    for permission in permissions
                ],
            )

    @staticmethod
    def validate_custom_permissions(permission_keys: list[str]) -> None:
        unique_keys = set(permission_keys)
        unknown = unique_keys - set(PERMISSIONS)
        reserved = unique_keys & OWNER_ONLY_PERMISSIONS
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown permissions: {', '.join(sorted(unknown))}",
            )
        if reserved:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Owner-only permissions cannot be assigned",
            )

    @staticmethod
    def require_assignable_role(
        business_id: UUID,
        role_id: UUID,
        db: Session,
    ) -> Role:
        role = (
            db.query(Role)
            .filter(
                Role.id == role_id,
                Role.business_id == business_id,
            )
            .first()
        )
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.name.lower() == "owner":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ownership cannot be assigned through member settings",
            )
        if not role.is_system_role:
            EntitlementService.require_feature(
                str(business_id),
                "custom_roles",
                db,
            )
        return role

    @staticmethod
    def require_custom_role(
        business_id: UUID,
        role_id: UUID,
        db: Session,
    ) -> Role:
        role = (
            db.query(Role)
            .filter(
                Role.id == role_id,
                Role.business_id == business_id,
            )
            .first()
        )
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
        if role.is_system_role:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Built-in roles cannot be changed",
            )
        return role

    @staticmethod
    def find_valid_invitation(
        token: str,
        db: Session,
    ) -> BusinessInvitation:
        invitation = (
            db.query(BusinessInvitation)
            .filter(
                BusinessInvitation.token_hash == MemberService.token_hash(token),
                BusinessInvitation.status == "pending",
            )
            .first()
        )
        if not invitation:
            raise HTTPException(
                status_code=404,
                detail="Invitation is invalid or no longer available",
            )
        if MemberService.is_expired(invitation.expires_at):
            invitation.status = "expired"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Invitation has expired",
            )
        return invitation

    @staticmethod
    def is_expired(
        expires_at: datetime,
        now: datetime | None = None,
    ) -> bool:
        comparison = now or datetime.now(timezone.utc)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= comparison

    @staticmethod
    def invitation_url(token: str) -> str:
        return f"{settings.APP_URL.rstrip('/')}/invitations/accept?token={token}"

    @staticmethod
    def send_invitation_email(
        recipient: str,
        business_name: str,
        role_name: str,
        accept_url: str,
    ) -> None:
        if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
            return
        message = EmailMessage()
        message["Subject"] = f"You're invited to {business_name} on StockWise"
        message["From"] = settings.SMTP_FROM_EMAIL
        message["To"] = recipient
        message.set_content(
            f"You've been invited as {role_name}.\n\n"
            f"Accept within {INVITATION_LIFETIME_DAYS} days:\n{accept_url}"
        )
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME:
                server.login(
                    settings.SMTP_USERNAME,
                    settings.SMTP_PASSWORD or "",
                )
            server.send_message(message)

    @staticmethod
    def add_audit_log(
        db: Session,
        business_id: UUID,
        user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        new_values: dict,
    ) -> None:
        db.add(
            AuditLog(
                business_id=business_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                new_values=new_values,
            )
        )
