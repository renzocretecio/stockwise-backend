import secrets
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models import BusinessMembership, User
from app.utils.security import (
    create_access_token,
    hash_password,
    verify_password,
)

class AuthService:
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = (
        "https://openidconnect.googleapis.com/v1/userinfo"
    )

    @staticmethod
    def register(
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        db: Session,
        *,
        commit: bool = True,
    ):
        """Register a new user"""
        normalized_email = email.strip().lower()
        user = db.query(User).filter(User.email == normalized_email).first()
        if user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already exists"
            )
        
        hashed_password = hash_password(password)
        new_user = User(
            email=normalized_email,
            password_hash=hashed_password,
            first_name=first_name,
            last_name=last_name
        )
        db.add(new_user)
        if commit:
            db.commit()
            db.refresh(new_user)
        else:
            db.flush()
        
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
        normalized_email = email.strip().lower()
        user = db.query(User).filter(User.email == normalized_email).first()
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
                "role": m.role.name,
                "slug": m.business.slug,
                "currency_code": m.business.currency_code,
                "timezone": m.business.timezone,
                "onboarding_completed": m.business.onboarding_completed,
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
    async def login_with_google(
        code: str,
        code_verifier: str,
        redirect_uri: str,
        db: Session,
    ) -> dict:
        """Exchange a Google code and link its verified identity."""
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google sign-in is not configured",
            )

        expected_redirect_uri = settings.GOOGLE_REDIRECT_URI or (
            f"{settings.APP_URL.rstrip('/')}/api/auth/google/callback"
        )
        if redirect_uri != expected_redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Google redirect URI",
            )

        try:
            async with httpx.AsyncClient(
                timeout=settings.GOOGLE_OAUTH_TIMEOUT_SECONDS,
            ) as client:
                token_response = await client.post(
                    AuthService.GOOGLE_TOKEN_URL,
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "code": code,
                        "code_verifier": code_verifier,
                        "grant_type": "authorization_code",
                        "redirect_uri": redirect_uri,
                    },
                )
                if not token_response.is_success:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Google authorization could not be verified",
                    )

                access_token = token_response.json().get("access_token")
                if not access_token:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Google did not return an access token",
                    )

                profile_response = await client.get(
                    AuthService.GOOGLE_USERINFO_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                    },
                )
                if not profile_response.is_success:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Google profile could not be verified",
                    )
                profile = profile_response.json()
        except HTTPException:
            raise
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google sign-in is temporarily unavailable",
            ) from exc

        subject = str(profile.get("sub", "")).strip()
        email = str(profile.get("email", "")).strip().lower()
        if not subject or not email or profile.get("email_verified") is not True:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google did not provide a verified email address",
            )

        user = db.query(User).filter(
            User.google_subject == subject
        ).first()
        if user is None:
            user = db.query(User).filter(User.email == email).first()
            if user and user.google_subject not in (None, subject):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This email is linked to another Google account",
                )

        is_new_user = user is None
        if user is None:
            first_name = str(profile.get("given_name", "")).strip()
            last_name = str(profile.get("family_name", "")).strip()
            user = User(
                email=email,
                google_subject=subject,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                first_name=first_name or email.split("@", 1)[0],
                last_name=last_name or None,
                is_active=True,
            )
            db.add(user)
            db.flush()
        elif not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is disabled",
            )
        elif user.google_subject is None:
            user.google_subject = subject

        user.last_login_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
            "access_token": create_access_token(user.id),
            "is_new_user": is_new_user,
        }

    @staticmethod
    def change_password(
        user: User,
        current_password: str,
        new_password: str,
        db: Session,
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        user.password_hash = hash_password(new_password)
        db.add(user)
        db.commit()
    
    @staticmethod
    def verify_access_to_business(
        user_id: str,
        business_id: str,
        db: Session,
    ) -> BusinessMembership:
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
