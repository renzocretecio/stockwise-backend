from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import StockBalance, StockMovement, InventoryCount, InventoryCountItem, Product
from datetime import datetime, date
from decimal import Decimal

class StockService:
    @staticmethod
    def adjust_stock(business_id: str, product_id: str, quantity_adjustment: Decimal, reason: str, user_id: str, db: Session):
        """Create stock adjustment"""
        stock_balance = db.query(StockBalance).filter(
            StockBalance.product_id == product_id,
            StockBalance.business_id == business_id
        ).first()
        
        if not stock_balance:
            raise ValueError("Stock balance not found")
        
        new_quantity = stock_balance.quantity + quantity_adjustment
        if new_quantity < 0:
            raise ValueError("Adjustment would result in negative stock")
        
        stock_balance.quantity = new_quantity
        db.add(stock_balance)
        
        movement = StockMovement(
            business_id=business_id,
            product_id=product_id,
            movement_type='adjustment',
            quantity=quantity_adjustment,
            reason=reason,
            created_by=user_id
        )
        db.add(movement)
        db.commit()
        
        return {
            "id": str(movement.id),
            "product_id": str(product_id),
            "quantity": float(quantity_adjustment),
            "reason": reason,
            "step": "adjusted"
        }
    
    @staticmethod
    def create_physical_count(business_id: str, user_id: str, db: Session):
        """Start physical inventory count"""
        count = InventoryCount(
            business_id=business_id,
            status='draft',
            count_date=date.today(),
            created_by=user_id
        )
        db.add(count)
        db.flush()
        
        products = db.query(Product).filter(
            Product.business_id == business_id,
            Product.is_active == True
        ).all()
        
        for product in products:
            stock_balance = db.query(StockBalance).filter(
                StockBalance.product_id == product.id
            ).first()
            
            count_item = InventoryCountItem(
                inventory_count_id=count.id,
                product_id=product.id,
                expected_quantity=stock_balance.quantity if stock_balance else 0
            )
            db.add(count_item)
        
        db.commit()
        db.refresh(count)
        
        return {
            "id": str(count.id),
            "status": count.status,
            "items_count": len(products),
            "step": "created"
        }
    
    @staticmethod
    def record_count_item(business_id: str, count_id: str, product_id: str, counted_quantity: Decimal, notes: str, user_id: str, db: Session):
        """Record counted quantity"""
        count_item = db.query(InventoryCountItem).join(
            InventoryCount
        ).filter(
            InventoryCount.business_id == business_id,
            InventoryCount.id == count_id,
            InventoryCountItem.product_id == product_id
        ).first()
        
        if not count_item:
            raise ValueError("Count item not found")
        
        count_item.counted_quantity = counted_quantity
        count_item.notes = notes
        count_item.counted_at = datetime.now()
        db.add(count_item)
        db.commit()
        
        return {
            "id": str(count_item.id),
            "expected": float(count_item.expected_quantity),
            "counted": float(counted_quantity),
            "variance": float(counted_quantity - count_item.expected_quantity),
            "step": "recorded"
        }
    
    @staticmethod
    def finalize_count(business_id: str, count_id: str, user_id: str, db: Session):
        """Finalize count and create adjustment movements"""
        count = db.query(InventoryCount).filter(
            InventoryCount.business_id == business_id,
            InventoryCount.id == count_id
        ).first()
        
        if not count:
            raise ValueError("Count not found")
        
        if count.status != 'draft':
            raise ValueError("Only draft counts can be finalized")
        
        movements_created = 0
        
        for item in count.items:
            if item.counted_quantity is None:
                continue
            
            variance = item.counted_quantity - item.expected_quantity
            
            if variance != 0:
                stock_balance = db.query(StockBalance).filter(
                    StockBalance.product_id == item.product_id
                ).first()
                
                stock_balance.quantity = item.counted_quantity
                db.add(stock_balance)
                
                movement = StockMovement(
                    business_id=business_id,
                    product_id=item.product_id,
                    movement_type='adjustment',
                    quantity=variance,
                    reason='physical_count',
                    reference_type='inventory_count',
                    reference_id=count.id,
                    created_by=user_id
                )
                db.add(movement)
                movements_created += 1
        
        count.status = 'finalized'
        count.finalized_by = user_id
        count.finalized_at = datetime.now()
        db.add(count)
        
        db.commit()
        db.refresh(count)
        
        return {
            "id": str(count.id),
            "status": count.status,
            "movements_created": movements_created,
            "step": "finalized"
        }
    
    @staticmethod
    def get_stock_movements(business_id: str, product_id: str = None, limit: int = 100, db: Session = None):
        """Get stock movements"""
        query = db.query(StockMovement).filter(
            StockMovement.business_id == business_id
        )
        
        if product_id:
            query = query.filter(StockMovement.product_id == product_id)
        
        movements = query.order_by(StockMovement.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": str(m.id),
                "product_id": str(m.product_id),
                "movement_type": m.movement_type,
                "quantity": float(m.quantity),
                "unit_cost": float(m.unit_cost) if m.unit_cost else None,
                "reason": m.reason,
                "reference_type": m.reference_type,
                "created_at": m.created_at.isoformat()
            }
            for m in movements
        ]
    
    @staticmethod
    def get_current_stock(business_id: str, db: Session):
        """Get current stock for all products"""
        balances = db.query(
            StockBalance.product_id,
            StockBalance.quantity,
            StockBalance.average_cost,
            Product.name,
            Product.sku,
            Product.reorder_point
        ).join(Product).filter(
            StockBalance.business_id == business_id
        ).all()
        
        return [
            {
                "product_id": str(b.product_id),
                "name": b.name,
                "sku": b.sku,
                "quantity": float(b.quantity),
                "average_cost": float(b.average_cost),
                "inventory_value": float(b.quantity * b.average_cost),
                "reorder_point": float(b.reorder_point),
                "status": "low" if b.quantity <= b.reorder_point else "ok"
            }
            for b in balances
        ]