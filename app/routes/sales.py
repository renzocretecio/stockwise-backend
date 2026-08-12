from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.utils.security import verify_token
from app.models import Business
from app.services.sale import SaleService
from pydantic import BaseModel
from typing import List

router = APIRouter(prefix="/sales", tags=["sales"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

class SaleItemRequest(BaseModel):
    product_id: str
    quantity: float
    unit_price: float

class CreateSaleRequest(BaseModel):
    reference_number: str = None
    items: List[SaleItemRequest]
    payment_method: str = "cash"
    tax_amount: float = 0
    discount_amount: float = 0
    notes: str = None

@router.post("/{business_id}")
async def create_sale(
    business_id: str,
    req: CreateSaleRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        verify_business_access(business_id, user_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        sale = SaleService.create_sale(business_id, req.dict(), user_id, db)
        return {"success": True, "sale": {"id": str(sale.id), "total_amount": float(sale.total_amount)}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}")
async def list_sales(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        verify_business_access(business_id, user_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        sales = SaleService.get_sales(business_id, db)
        return {
            "success": True,
            "sales": [
                {
                    "id": str(s.id),
                    "reference_number": s.reference_number,
                    "status": s.status,
                    "total_amount": float(s.total_amount),
                    "sale_date": s.sale_date.isoformat()
                }
                for s in sales
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def verify_business_access(business_id: str, user_id: str, db: Session):
    """Verify user has access to business"""
    from app.services.auth import AuthService
    return AuthService.verify_access_to_business(user_id, business_id, db)