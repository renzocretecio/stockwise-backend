from sqlalchemy.orm import Session
from app.models import Purchase, PurchaseItem, Product, StockBalance, StockMovement
from datetime import datetime, date
from decimal import Decimal

class PurchaseService:
    @staticmethod
    def create_purchase(business_id: str, data: dict, user_id: str, db: Session):
        """Create a draft purchase"""
        purchase = Purchase(
            business_id=business_id,
            supplier_id=data.get("supplier_id"),
            reference_number=data.get("reference_number"),
            purchase_date=data.get("purchase_date", date.today()),
            notes=data.get("notes"),
            created_by=user_id,
            status='draft'
        )
        db.add(purchase)
        db.flush()
        
        subtotal = Decimal("0")
        for item in data.get("items", []):
            product_id = item.get("product_id")
            quantity = Decimal(str(item.get("quantity")))
            unit_cost = Decimal(str(item.get("unit_cost")))
            line_total = quantity * unit_cost
            
            purchase_item = PurchaseItem(
                purchase_id=purchase.id,
                product_id=product_id,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=line_total
            )
            db.add(purchase_item)
            subtotal += line_total
        
        tax = Decimal(str(data.get("tax_amount", 0)))
        discount = Decimal(str(data.get("discount_amount", 0)))
        purchase.subtotal = subtotal
        purchase.tax_amount = tax
        purchase.discount_amount = discount
        purchase.total_amount = subtotal + tax - discount
        
        db.commit()
        db.refresh(purchase)
        
        return {
            "id": str(purchase.id),
            "status": purchase.status,
            "total_amount": float(purchase.total_amount),
            "step": "created"
        }
    
    @staticmethod
    def receive_purchase(business_id: str, purchase_id: str, user_id: str, db: Session):
        """Receive purchase and create stock movements"""
        purchase = db.query(Purchase).filter(
            Purchase.business_id == business_id,
            Purchase.id == purchase_id
        ).first()
        
        if not purchase:
            raise ValueError("Purchase not found")
        
        if purchase.status != 'draft':
            raise ValueError("Only draft purchases can be received")
        
        movements = []
        
        for item in purchase.items:
            stock_balance = db.query(StockBalance).filter(
                StockBalance.product_id == item.product_id,
                StockBalance.business_id == business_id
            ).first()
            
            if not stock_balance:
                raise ValueError(f"Stock balance not found for product {item.product_id}")
            
            # Calculate weighted average cost
            old_value = stock_balance.quantity * stock_balance.average_cost
            new_value = item.quantity * item.unit_cost
            total_quantity = stock_balance.quantity + item.quantity
            
            if total_quantity > 0:
                stock_balance.average_cost = (old_value + new_value) / total_quantity
            
            stock_balance.quantity += item.quantity
            db.add(stock_balance)
            
            # Create stock movement
            movement = StockMovement(
                business_id=business_id,
                product_id=item.product_id,
                movement_type='purchase',
                quantity=item.quantity,
                unit_cost=item.unit_cost,
                reference_type='purchase',
                reference_id=purchase.id,
                created_by=user_id
            )
            db.add(movement)
            movements.append(movement)
        
        purchase.status = 'received'
        purchase.received_at = datetime.now()
        purchase.received_by = user_id
        db.commit()
        db.refresh(purchase)
        
        return {
            "id": str(purchase.id),
            "status": purchase.status,
            "movements_created": len(movements),
            "step": "received"
        }
    
    @staticmethod
    def get_purchases(business_id: str, db: Session):
        """Get all purchases"""
        purchases = db.query(Purchase).filter(
            Purchase.business_id == business_id
        ).order_by(Purchase.purchase_date.desc()).all()
        
        return [
            {
                "id": str(p.id),
                "reference_number": p.reference_number,
                "status": p.status,
                "total_amount": float(p.total_amount),
                "purchase_date": p.purchase_date.isoformat()
            }
            for p in purchases
        ]