from sqlalchemy.orm import Session
from app.models import Sale, SaleItem, Product, StockBalance, StockMovement
from datetime import datetime
from decimal import Decimal

class SaleService:
    @staticmethod
    def create_sale(business_id: str, data: dict, user_id: str, db: Session):
        """Create and complete sale with stock movements"""
        sale = Sale(
            business_id=business_id,
            reference_number=data.get("reference_number"),
            payment_method=data.get("payment_method"),
            notes=data.get("notes"),
            created_by=user_id,
            status='completed'
        )
        db.add(sale)
        db.flush()
        
        subtotal = Decimal("0")
        movements = []
        
        for item in data.get("items", []):
            product_id = item.get("product_id")
            quantity = Decimal(str(item.get("quantity")))
            unit_price = Decimal(str(item.get("unit_price")))
            
            stock_balance = db.query(StockBalance).filter(
                StockBalance.product_id == product_id,
                StockBalance.business_id == business_id
            ).first()
            
            if not stock_balance or stock_balance.quantity < quantity:
                raise ValueError(f"Insufficient stock for product {product_id}")
            
            unit_cost = stock_balance.average_cost
            line_total = quantity * unit_price
            
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=unit_cost,
                line_total=line_total
            )
            db.add(sale_item)
            subtotal += line_total
            
            # Update stock
            stock_balance.quantity -= quantity
            db.add(stock_balance)
            
            # Create movement
            movement = StockMovement(
                business_id=business_id,
                product_id=product_id,
                movement_type='sale',
                quantity=-quantity,
                unit_cost=unit_cost,
                reference_type='sale',
                reference_id=sale.id,
                created_by=user_id
            )
            db.add(movement)
            movements.append(movement)
        
        tax = Decimal(str(data.get("tax_amount", 0)))
        discount = Decimal(str(data.get("discount_amount", 0)))
        sale.subtotal = subtotal
        sale.tax_amount = tax
        sale.discount_amount = discount
        sale.total_amount = subtotal + tax - discount
        
        db.commit()
        db.refresh(sale)
        
        return {
            "id": str(sale.id),
            "status": sale.status,
            "total_amount": float(sale.total_amount),
            "movements_created": len(movements),
            "step": "completed"
        }
    
    @staticmethod
    def get_sales(business_id: str, db: Session):
        """Get all sales"""
        sales = db.query(Sale).filter(
            Sale.business_id == business_id
        ).order_by(Sale.sale_date.desc()).all()
        
        return [
            {
                "id": str(s.id),
                "reference_number": s.reference_number,
                "status": s.status,
                "total_amount": float(s.total_amount),
                "sale_date": s.sale_date.isoformat()
            }
            for s in sales
        ]