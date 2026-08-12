from sqlalchemy.orm import Session
from app.models import Business, BusinessMembership, User, Role
from datetime import datetime

class BusinessService:
    @staticmethod
    def create_business(user_id: str, name: str, slug: str, currency_code: str, timezone: str, db: Session):
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
        
        # Add creator as owner
        membership = BusinessMembership(
            business_id=business.id,
            user_id=user_id,
            role_id=owner_role.id,
            status='active',
            joined_at=datetime.now()
        )
        db.add(membership)
        
        db.commit()
        db.refresh(business)
        return business
    
    @staticmethod
    def get_business(business_id: str, db: Session):
        """Get business by ID"""
        return db.query(Business).filter(Business.id == business_id).first()
    
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
                "slug": m.business.slug
            }
            for m in memberships
        ]