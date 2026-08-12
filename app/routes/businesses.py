from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.utils.security import verify_token
from app.services.auth import AuthService
from app.services.business import BusinessService
from pydantic import BaseModel

router = APIRouter(prefix="/businesses", tags=["businesses"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

@router.get("/my-businesses")
async def get_my_businesses(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
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
    user_id: str = Depends(get_current_user_id)
):
    """Get business details (verify user access first)"""
    try:
        # Verify access
        membership = AuthService.verify_access_to_business(user_id, business_id, db)
        
        business = BusinessService.get_business(business_id, db)
        return {
            "success": True,
            "business": {
                "id": str(business.id),
                "name": business.name,
                "slug": business.slug,
                "currency_code": business.currency_code,
                "timezone": business.timezone
            },
            "user_role": membership.role.name
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))