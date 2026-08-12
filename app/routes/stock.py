from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.utils.security import verify_token
from app.models import Business
from app.services.stock import StockService
from pydantic import BaseModel
from decimal import Decimal
from app.services.auth import AuthService

router = APIRouter(prefix="/stock", tags=["stock"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

class AdjustStockRequest(BaseModel):
    product_id: str
    quantity_adjustment: float
    reason: str

@router.post("/{business_id}/adjust")
async def adjust_stock(
    business_id: str,
    req: AdjustStockRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        movement = StockService.adjust_stock(
            business_id,
            req.product_id,
            Decimal(str(req.quantity_adjustment)),
            req.reason,
            user_id,
            db
        )
        return {"success": True, "movement": {"id": str(movement.id)}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/count/start")
async def start_physical_count(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        count = StockService.create_physical_count(business_id, user_id, db)
        return {"success": True, "count": {"id": str(count.id), "status": count.status}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/count/{count_id}/finalize")
async def finalize_count(
    business_id: str,
    count_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        count = StockService.finalize_count(business_id, count_id, user_id, db)
        return {"success": True, "count": {"id": str(count.id), "status": count.status}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}/movements")
async def get_movements(
    business_id: str,
    product_id: str = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")

        movements = StockService.get_stock_movements(business_id, product_id, 100, db)
        return {
            "success": True,
            "movements": [
                {
                    "id": str(m.id),
                    "product_id": str(m.product_id),
                    "movement_type": m.movement_type,
                    "quantity": float(m.quantity),
                    "reason": m.reason,
                    "created_at": m.created_at.isoformat()
                }
                for m in movements
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))