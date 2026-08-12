from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.utils.security import verify_token
from app.services.auth import AuthService
from app.services.product import ProductService
from app.services.purchase import PurchaseService
from app.services.sale import SaleService
from app.services.stock import StockService
from app.services.reports import ReportService
from pydantic import BaseModel
from typing import List
from datetime import date
from decimal import Decimal

router = APIRouter(prefix="/transactions", tags=["transactions"])

def get_current_user_id(authorization: str = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.split(" ")[1]
    return verify_token(token)

# ===== PRODUCT =====

class CreateProductRequest(BaseModel):
    name: str
    sku: str = None
    cost_price: float
    selling_price: float
    reorder_point: float = 0
    supplier_id: str = None

@router.post("/{business_id}/product")
async def create_product(
    business_id: str,
    req: CreateProductRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = ProductService.create_product(business_id, req.dict(), db)
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== PURCHASE =====

class PurchaseItemRequest(BaseModel):
    product_id: str
    quantity: float
    unit_cost: float

class CreatePurchaseRequest(BaseModel):
    supplier_id: str
    reference_number: str = None
    items: List[PurchaseItemRequest]
    tax_amount: float = 0
    discount_amount: float = 0

@router.post("/{business_id}/purchase")
async def create_purchase(
    business_id: str,
    req: CreatePurchaseRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = PurchaseService.create_purchase(business_id, req.dict(), user_id, db)
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/purchase/{purchase_id}/receive")
async def receive_purchase(
    business_id: str,
    purchase_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = PurchaseService.receive_purchase(business_id, purchase_id, user_id, db)
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== SALE =====

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

@router.post("/{business_id}/sale")
async def create_sale(
    business_id: str,
    req: CreateSaleRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = SaleService.create_sale(business_id, req.dict(), user_id, db)
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== STOCK =====

class AdjustStockRequest(BaseModel):
    product_id: str
    quantity_adjustment: float
    reason: str

@router.post("/{business_id}/stock/adjust")
async def adjust_stock(
    business_id: str,
    req: AdjustStockRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = StockService.adjust_stock(
            business_id,
            req.product_id,
            Decimal(str(req.quantity_adjustment)),
            req.reason,
            user_id,
            db
        )
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/inventory-count")
async def start_inventory_count(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = StockService.create_physical_count(business_id, user_id, db)
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class RecordCountRequest(BaseModel):
    counted_quantity: float
    notes: str = None

@router.post("/{business_id}/inventory-count/{count_id}/record/{product_id}")
async def record_count(
    business_id: str,
    count_id: str,
    product_id: str,
    req: RecordCountRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = StockService.record_count_item(
            business_id,
            count_id,
            product_id,
            Decimal(str(req.counted_quantity)),
            req.notes,
            user_id,
            db
        )
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{business_id}/inventory-count/{count_id}/finalize")
async def finalize_inventory_count(
    business_id: str,
    count_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        result = StockService.finalize_count(business_id, count_id, user_id, db)
        return {"success": True, "data": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}/stock-movements")
async def get_stock_movements(
    business_id: str,
    product_id: str = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        movements = StockService.get_stock_movements(business_id, product_id, limit, db)
        return {"success": True, "data": movements}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ===== REPORTS =====

@router.get("/{business_id}/report/inventory")
async def inventory_report(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        report = ReportService.get_inventory_report(business_id, db)
        return {"success": True, "data": report}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}/report/sales")
async def sales_report(
    business_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        report = ReportService.get_sales_report(business_id, days, db)
        return {"success": True, "data": report}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}/report/purchases")
async def purchases_report(
    business_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        report = ReportService.get_purchase_report(business_id, days, db)
        return {"success": True, "data": report}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}/report/stock-movements")
async def stock_movements_report(
    business_id: str,
    days: int = 30,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        report = ReportService.get_stock_movement_report(business_id, days, db)
        return {"success": True, "data": report}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{business_id}/stock/current")
async def get_current_stock(
    business_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    try:
        AuthService.verify_access_to_business(user_id, business_id, db)
        stock = StockService.get_current_stock(business_id, db)
        return {"success": True, "data": stock}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))