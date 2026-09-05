from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.core.security import get_current_user
from app.models import BusinessMembership, User
from app.models.permission import Permission, RolePermission
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    SignUpWithBusinessRequest,
    UserProfileUpdate,
)
from app.services.auth import AuthService
from app.services.business import BusinessService

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup")
async def signup(req: SignUpWithBusinessRequest, db: Session = Depends(get_db)):
    """Register new user and create their first business"""
    try:
        # Register user
        user_result = AuthService.register(
            req.email,
            req.password,
            req.first_name,
            req.last_name or "",
            db,
            commit=False,
        )
        
        user_id = user_result["user"]["id"]
        
        # Create business
        business_slug = req.business_slug or (
            BusinessService.generate_unique_slug(req.business_name, db)
        )
        business = BusinessService.create_business(
            user_id,
            req.business_name,
            business_slug,
            req.currency_code,
            req.timezone,
            db,
            commit=False,
        )

        db.commit()
        db.refresh(business)
        
        return {
            "success": True,
            "user": user_result["user"],
            "business": {
                "id": str(business.id),
                "name": business.name,
                "slug": business.slug,
                "currency_code": business.currency_code,
                "timezone": business.timezone,
                "onboarding_completed": business.onboarding_completed,
            },
            "access_token": user_result["access_token"]
        }
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create account",
        ) from e

@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Login user and return their businesses"""
    try:
        result = AuthService.login(req.email, req.password, db)
        return {"success": True, **result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/me")
def get_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    memberships = db.query(BusinessMembership).filter(
        BusinessMembership.user_id == current_user.id,
        BusinessMembership.status == 'active'
    ).all()

    business_payload = []
    user_permissions = set()

    for membership in memberships:
        is_owner = (
            membership.role
            and getattr(membership.role, "is_system_role", False)
            and membership.role.name.lower() == "owner"
        )
        if is_owner:
            permission_rows = db.query(Permission.key).all()
        else:
            permission_rows = (
                db.query(Permission.key)
                .join(
                    RolePermission,
                    RolePermission.permission_id == Permission.id,
                )
                .filter(RolePermission.role_id == membership.role_id)
                .all()
            )
        permissions = sorted({row[0] for row in permission_rows})
        user_permissions.update(permissions)

        business_payload.append({
            "id": str(membership.business.id),
            "name": membership.business.name,
            "slug": membership.business.slug,
            "currency_code": getattr(
                membership.business,
                "currency_code",
                "PHP",
            ),
            "timezone": getattr(
                membership.business,
                "timezone",
                "Asia/Manila",
            ),
            "onboarding_completed": getattr(
                membership.business,
                "onboarding_completed",
                True,
            ),
            "role": membership.role.name if membership.role else None,
            "permissions": permissions,
        })

    return {
        "success": True,
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "permissions": sorted(user_permissions),
        },
        "businesses": business_payload,
    }


@router.patch("/me")
def update_user_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.first_name = payload.first_name
    current_user.last_name = payload.last_name
    db.commit()
    db.refresh(current_user)
    return {
        "success": True,
        "user": {
            "id": str(current_user.id),
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
        },
    }


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    AuthService.change_password(
        current_user,
        payload.current_password,
        payload.new_password,
        db,
    )
    return {"success": True, "message": "Password changed successfully"}
