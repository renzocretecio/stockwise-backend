from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.auth import AuthService
from app.services.business import BusinessService
from app.schemas.auth import LoginRequest
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

class SignUpWithBusinessRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str = None
    business_name: str
    business_slug: str

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
            db
        )
        
        user_id = user_result["user"]["id"]
        
        # Create business
        business = BusinessService.create_business(
            user_id,
            req.business_name,
            req.business_slug,
            "PHP",
            "Asia/Manila",
            db
        )
        
        return {
            "success": True,
            "user": user_result["user"],
            "business": {
                "id": str(business.id),
                "name": business.name,
                "slug": business.slug
            },
            "access_token": user_result["access_token"]
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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