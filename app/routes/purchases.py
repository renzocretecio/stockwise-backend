from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.auth import AuthService
from app.utils.security import verify_token
from app.models import Business
from app.services.purchase import PurchaseService
from pydantic import BaseModel
from typing import List
from datetime import date

router = APIRouter(prefix="/purchases", tags=["purchases"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

class PurchaseItemRequest(BaseModel):
    product_id: str
    quantity: float
    unit_cost: float

class CreatePurchaseRequest(BaseModel):
    supplier_id: str
    reference_number: str = None
    purchase_date: date = None
    items: List[PurchaseItemRequest]
    tax_amount: float = 0
    discount_amount: float = 0
    notes: str = None

@router.post("/{business_id}")
async def create_purchase(
    business_id: str,
    req: CreatePurchaseRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
    
        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        purchase = PurchaseService.create_purchase(business_id, req.dict(), user_id, db)
        return {"success": True, "purchase": {"id": str(purchase.id), "status": purchase.status}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/{purchase_id}/receive")
async def receive_purchase(
    business_id: str,
    purchase_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        purchase = PurchaseService.receive_purchase(business_id, purchase_id, user_id, db)
        return {"success": True, "purchase": {"id": str(purchase.id), "status": purchase.status}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}")
async def list_purchases(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        purchases = PurchaseService.get_purchases(business_id, db)
        return {
            "success": True,
            "purchases": [
                {
                    "id": str(p.id),
                    "reference_number": p.reference_number,
                    "status": p.status,
                    "total_amount": float(p.total_amount),
                    "purchase_date": p.purchase_date.isoformat()
                }
                for p in purchases
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))