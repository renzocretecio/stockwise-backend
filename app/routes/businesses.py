from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models import BusinessMembership
from app.utils.security import verify_token
from app.config.permissions import RequestContext, require_permission
from app.schemas.business import BusinessCreate, BusinessProfileUpdate
from app.services.business import BusinessService
from app.services.entitlements import EntitlementService

router = APIRouter(prefix="/businesses", tags=["businesses"])


def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)


@router.post("")
async def create_business(
    payload: BusinessCreate,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    has_business = (
        db.query(BusinessMembership.id)
        .filter(
            BusinessMembership.user_id == user_id,
        )
        .first()
    )
    grant_pro_trial = (
        has_business is None
        and not EntitlementService.user_has_used_pro_trial(user_id, db)
    )
    slug = BusinessService.generate_unique_slug(payload.name, db)
    business = BusinessService.create_business(
        user_id,
        payload.name,
        slug,
        "PHP",
        "Asia/Manila",
        db,
        grant_pro_trial=grant_pro_trial,
    )
    return {
        "success": True,
        "business": {
            "id": str(business.id),
            "name": business.name,
            "slug": business.slug,
            "currency_code": business.currency_code,
            "timezone": business.timezone,
            "role": "owner",
            "onboarding_completed": business.onboarding_completed,
        },
    }


@router.get("/my-businesses")
async def get_my_businesses(
    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    """Get all businesses current user is member of"""
    try:
        businesses = BusinessService.get_user_businesses(user_id, db)
        return {"success": True, "businesses": businesses}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{business_id}")
async def get_business(
    business_id: str,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("business.read")),
):
    """Get business details (verify user access first)"""
    try:
        if str(context.business_id) != business_id:
            raise HTTPException(
                status_code=403,
                detail="The path does not match the active business",
            )

        business = BusinessService.get_business(business_id, db)
        return {
            "success": True,
            "business": {
                "id": str(business.id),
                "name": business.name,
                "slug": business.slug,
                "currency_code": business.currency_code,
                "timezone": business.timezone,
                "industry": business.industry,
                "email": business.email,
                "phone": business.phone,
                "address": business.address,
                "onboarding_completed": business.onboarding_completed,
            },
            "user_role": context.membership.role.name,
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{business_id}")
async def update_business_profile(
    business_id: str,
    payload: BusinessProfileUpdate,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("business.update")),
):
    if str(context.business_id) != business_id:
        raise HTTPException(
            status_code=403,
            detail="The path does not match the active business",
        )

    business = BusinessService.get_business(business_id, db)
    business = BusinessService.update_profile(business, payload, db)
    return {
        "success": True,
        "business": {
            "id": str(business.id),
            "name": business.name,
            "currency_code": business.currency_code,
            "timezone": business.timezone,
            "industry": business.industry,
            "email": business.email,
            "phone": business.phone,
            "address": business.address,
            "onboarding_completed": business.onboarding_completed,
        },
    }
