from sqlalchemy.orm import Session
from app.models import Product, Supplier, StockBalance
from decimal import Decimal

class ProductService:
    @staticmethod
    def create_product(business_id: str, data: dict, db: Session):
        """Create a new product with stock balance"""
        product = Product(
            business_id=business_id,
            supplier_id=data.get("supplier_id"),
            sku=data.get("sku"),
            barcode=data.get("barcode"),
            name=data.get("name"),
            normalized_name=data.get("name", "").lower(),
            description=data.get("description"),
            category=data.get("category"),
            brand=data.get("brand"),
            unit=data.get("unit", "unit"),
            cost_price=Decimal(str(data.get("cost_price", 0))),
            selling_price=Decimal(str(data.get("selling_price", 0))),
            reorder_point=Decimal(str(data.get("reorder_point", 0))),
            safety_stock=Decimal(str(data.get("safety_stock", 0))),
            lead_time_days=data.get("lead_time_days", 3),
            is_perishable=data.get("is_perishable", False),
        )
        db.add(product)
        db.flush()
        
        # Create stock balance
        stock_balance = StockBalance(
            business_id=business_id,
            product_id=product.id,
            quantity=0,
            reserved_quantity=0,
            average_cost=Decimal("0")
        )
        db.add(stock_balance)
        db.commit()
        db.refresh(product)
        
        return {
            "id": str(product.id),
            "name": product.name,
            "sku": product.sku,
            "cost_price": float(product.cost_price),
            "selling_price": float(product.selling_price),
            "status": "created"
        }
    
    @staticmethod
    def get_products(business_id: str, db: Session):
        """Get all products for a business"""
        products = db.query(Product).filter(
            Product.business_id == business_id,
            Product.is_active == True
        ).all()
        
        return [
            {
                "id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "cost_price": float(p.cost_price),
                "selling_price": float(p.selling_price)
            }
            for p in products
        ]
    
    @staticmethod
    def get_product(business_id: str, product_id: str, db: Session):
        """Get product by ID"""
        return db.query(Product).filter(
            Product.business_id == business_id,
            Product.id == product_id
        ).first()