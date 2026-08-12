from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import User, Business, BusinessMembership, Role
from app.utils.security import hash_password, verify_password, create_access_token
from fastapi import HTTPException, status
from datetime import datetime

class AuthService:
    @staticmethod
    def register(email: str, password: str, first_name: str, last_name: str, db: Session):
        """Register a new user"""
        user = db.query(User).filter(User.email == email).first()
        if user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already exists"
            )
        
        hashed_password = hash_password(password)
        new_user = User(
            email=email,
            password_hash=hashed_password,
            first_name=first_name,
            last_name=last_name
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        token = create_access_token(new_user.id)
        return {
            "user": {
                "id": str(new_user.id),
                "email": new_user.email,
                "first_name": new_user.first_name
            },
            "access_token": token
        }
    
    @staticmethod
    def login(email: str, password: str, db: Session):
        """Login user"""
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        token = create_access_token(user.id)
        
        # Get businesses user is member of
        memberships = db.query(BusinessMembership).filter(
            BusinessMembership.user_id == user.id,
            BusinessMembership.status == 'active'
        ).all()
        
        businesses = [
            {
                "id": str(m.business_id),
                "name": m.business.name,
                "role": m.role.name
            }
            for m in memberships
        ]
        
        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name
            },
            "businesses": businesses,
            "access_token": token
        }
    
    @staticmethod
    def verify_access_to_business(user_id: str, business_id: str, db: Session) -> BusinessMembership:
        """Verify user has access to business"""
        membership = db.query(BusinessMembership).filter(
            and_(
                BusinessMembership.user_id == user_id,
                BusinessMembership.business_id == business_id,
                BusinessMembership.status == 'active'
            )
        ).first()
        
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this business"
            )
        
        return membership