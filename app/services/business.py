import re
import unicodedata
from sqlalchemy.orm import Session
from app.models import Business, BusinessMembership, User, Role
from app.models.permission import Permission, RolePermission
from datetime import datetime, timezone

from app.schemas.business import BusinessProfileUpdate

class BusinessService:
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
        timezone: str,
        db: Session,
        *,
        commit: bool = True,
    ):
        """Create a new business and make user the owner"""
        existing = db.query(Business).filter(Business.slug == slug).first()
        if existing:
            raise ValueError("Business slug already exists")
        
        business = Business(
            name=name,
            slug=slug,
            currency_code=currency_code,
            timezone=timezone
        )
        db.add(business)
        db.flush()
        
        # Create owner role if not exists
        owner_role = db.query(Role).filter(
            Role.business_id == business.id,
            Role.name == 'owner'
        ).first()
        
        if not owner_role:
            owner_role = Role(
                business_id=business.id,
                name='owner',
                description='Business owner',
                is_system_role=True
            )
            db.add(owner_role)
            db.flush()

        # Business owners receive every registered permission. Permissions
        # are linked explicitly so the same authorization path is used for
        # owners and custom roles; the role name itself grants no access.
        permissions = db.query(Permission).all()
        existing_permission_ids = {
            row[0]
            for row in db.query(RolePermission.permission_id)
            .filter(RolePermission.role_id == owner_role.id)
            .all()
        }
        permission_links = [
            {
                "role_id": owner_role.id,
                "permission_id": permission.id,
            }
            for permission in permissions
            if permission.id not in existing_permission_ids
        ]
        if permission_links:
            # Role uses the application's SQLAlchemy Base while the
            # permission models use SQLModel metadata. A direct insert avoids
            # cross-metadata ORM dependency sorting during flush.
            db.execute(RolePermission.__table__.insert(), permission_links)
        
        # Add creator as owner
        membership = BusinessMembership(
            business_id=business.id,
            user_id=user_id,
            role_id=owner_role.id,
            status='active',
            joined_at=datetime.now()
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
        memberships = db.query(BusinessMembership).filter(
            BusinessMembership.user_id == user_id,
            BusinessMembership.status == 'active'
        ).all()
        
        return [
            {
                "id": str(m.business_id),
                "name": m.business.name,
                "role": m.role.name,
                "slug": m.business.slug,
                "currency_code": m.business.currency_code,
                "timezone": m.business.timezone,
                "onboarding_completed": m.business.onboarding_completed,
            }
            for m in memberships
        ]
