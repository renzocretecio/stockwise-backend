from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services.auth import AuthService
from app.utils.security import verify_token
from app.models import Business
from app.services.product import ProductService
from pydantic import BaseModel

router = APIRouter(prefix="/products", tags=["products"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

class CreateProductRequest(BaseModel):
    name: str
    sku: str = None
    barcode: str = None
    supplier_id: str = None
    cost_price: float
    selling_price: float
    reorder_point: float = 0
    safety_stock: float = 0
    category: str = None
    brand: str = None
    unit: str = "unit"
    lead_time_days: int = 3
    is_perishable: bool = False

@router.post("/{business_id}")
async def create_product(
    business_id: str,
    req: CreateProductRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        product = ProductService.create_product(business_id, req.dict(), db)
        return {"success": True, "product": {"id": str(product.id), "name": product.name}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}")
async def list_products(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)

        business = db.query(Business).filter(Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        products = ProductService.get_products(business_id, db)
        return {
            "success": True,
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "sku": p.sku,
                    "cost_price": float(p.cost_price),
                    "selling_price": float(p.selling_price),
                    "reorder_point": float(p.reorder_point)
                }
                for p in products
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))