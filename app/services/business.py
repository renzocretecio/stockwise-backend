import re
import unicodedata
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models import Business, BusinessMembership, BusinessSubscription, User, Role
from app.models.permission import Permission, RolePermission
from app.config.rbac import (
    SYSTEM_ROLE_DESCRIPTIONS,
    SYSTEM_ROLE_PERMISSIONS,
)
from datetime import datetime, timedelta, timezone

from app.schemas.business import BusinessProfileUpdate
from app.services.entitlements import EntitlementService, PRO_TRIAL_DAYS


class BusinessService:
    @staticmethod
    def ensure_system_roles(business_id: str, db: Session) -> dict[str, Role]:
        """Create and synchronize the built-in roles for one business."""
        permissions = {
            permission.key: permission for permission in db.query(Permission).all()
        }
        roles: dict[str, Role] = {}

        for role_name, permission_keys in SYSTEM_ROLE_PERMISSIONS.items():
            role = (
                db.query(Role)
                .filter(
                    Role.business_id == business_id,
                    func.lower(Role.name) == role_name,
                )
                .first()
            )
            if not role:
                role = Role(
                    business_id=business_id,
                    name=role_name,
                    description=SYSTEM_ROLE_DESCRIPTIONS[role_name],
                    is_system_role=True,
                )
                db.add(role)
                db.flush()

            roles[role_name] = role
            existing_ids = {
                row[0]
                for row in db.query(RolePermission.permission_id)
                .filter(RolePermission.role_id == role.id)
                .all()
            }
            links = [
                {
                    "role_id": role.id,
                    "permission_id": permissions[key].id,
                }
                for key in permission_keys
                if key in permissions and permissions[key].id not in existing_ids
            ]
            if links:
                db.execute(RolePermission.__table__.insert(), links)

        return roles

    @staticmethod
    def generate_unique_slug(name: str, db: Session) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
        base_slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower())
        base_slug = base_slug.strip("-")[:140] or "business"
        slug = base_slug
        suffix = 2

        while db.query(Business.id).filter(Business.slug == slug).first():
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        return slug

    @staticmethod
    def create_business(
        user_id: str,
        name: str,
        slug: str,
        currency_code: str,
        timezone_name: str,
        db: Session,
        *,
        commit: bool = True,
        grant_pro_trial: bool = False,
    ):
        """Create a new business and make user the owner"""
        existing = db.query(Business).filter(Business.slug == slug).first()
        if existing:
            raise ValueError("Business slug already exists")

        business = Business(
            name=name, slug=slug, currency_code=currency_code, timezone=timezone_name
        )
        db.add(business)
        db.flush()

        if grant_pro_trial:
            trial_started_at = datetime.now(timezone.utc)
            updated_users = (
                db.query(User)
                .filter(
                    User.id == user_id,
                    User.pro_trial_used_at.is_(None),
                )
                .update(
                    {User.pro_trial_used_at: trial_started_at},
                    synchronize_session=False,
                )
            )
            if updated_users != 1:
                raise ValueError("The user has already used a Pro trial")
            subscription = BusinessSubscription(
                business_id=business.id,
                plan="pro",
                status="trialing",
                provider="manual",
                trial_started_at=trial_started_at,
                trial_ends_at=(trial_started_at + timedelta(days=PRO_TRIAL_DAYS)),
            )
        else:
            subscription = BusinessSubscription(
                business_id=business.id,
                plan="free",
                status="active",
                provider="manual",
            )
        db.add(subscription)

        roles = BusinessService.ensure_system_roles(business.id, db)
        owner_role = roles["owner"]

        # Add creator as owner
        membership = BusinessMembership(
            business_id=business.id,
            user_id=user_id,
            role_id=owner_role.id,
            status="active",
            joined_at=datetime.now(),
        )
        db.add(membership)

        if commit:
            db.commit()
            db.refresh(business)
        else:
            db.flush()
        return business

    @staticmethod
    def get_business(business_id: str, db: Session):
        """Get business by ID"""
        return db.query(Business).filter(Business.id == business_id).first()

    @staticmethod
    def update_profile(
        business: Business,
        payload: BusinessProfileUpdate,
        db: Session,
    ) -> Business:
        updates = payload.model_dump(exclude={"complete_onboarding"})
        for field, value in updates.items():
            setattr(business, field, value)

        if payload.complete_onboarding:
            business.onboarding_completed = True
            business.onboarding_completed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(business)
        return business

    @staticmethod
    def get_user_businesses(user_id: str, db: Session):
        """Get all businesses a user is member of"""
        memberships = (
            db.query(BusinessMembership)
            .filter(
                BusinessMembership.user_id == user_id,
                BusinessMembership.status == "active",
            )
            .all()
        )

        businesses = []
        for membership in memberships:
            subscription = getattr(membership.business, "subscription", None)
            businesses.append(
                {
                    "id": str(membership.business_id),
                    "name": membership.business.name,
                    "role": membership.role.name,
                    "slug": membership.business.slug,
                    "currency_code": membership.business.currency_code,
                    "timezone": membership.business.timezone,
                    "onboarding_completed": (membership.business.onboarding_completed),
                    "plan": EntitlementService.effective_plan(subscription),
                    "subscription_status": (
                        EntitlementService.effective_status(subscription)
                    ),
                }
            )
        return businesses
