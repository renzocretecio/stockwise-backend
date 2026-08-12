from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.utils.security import verify_token
from app.models import Business
from app.services.supplier import SupplierService
from pydantic import BaseModel
from app.services.auth import AuthService

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

class CreateSupplierRequest(BaseModel):
    name: str
    contact_person: str = None
    email: str = None
    phone: str = None
    address: str = None
    payment_terms: str = None
    lead_time_days: int = 3

@router.post("/{business_id}")
async def create_supplier(
    business_id: str,
    req: CreateSupplierRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        supplier = SupplierService.create_supplier(business_id, req.dict(), db)
        return {"success": True, "supplier": {"id": str(supplier.id), "name": supplier.name}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}")
async def list_suppliers(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        suppliers = SupplierService.get_suppliers(business_id, db)
        return {
            "success": True,
            "suppliers": [
                {
                    "id": str(s.id),
                    "name": s.name,
                    "contact_person": s.contact_person,
                    "lead_time_days": s.lead_time_days
                }
                for s in suppliers
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))