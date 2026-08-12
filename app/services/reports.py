from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models import StockBalance, StockMovement, Sale, SaleItem, Purchase, PurchaseItem, Product
from datetime import datetime, timedelta
from decimal import Decimal

class ReportService:
    @staticmethod
    def get_inventory_report(business_id: str, db: Session):
        """Generate inventory report"""
        balances = db.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.category,
            StockBalance.quantity,
            StockBalance.average_cost,
            Product.reorder_point,
            Product.safety_stock
        ).join(StockBalance).filter(
            StockBalance.business_id == business_id,
            Product.is_active == True
        ).all()
        
        total_inventory_value = Decimal("0")
        low_stock_items = 0
        items = []
        
        for b in balances:
            inventory_value = b.quantity * b.average_cost
            total_inventory_value += inventory_value
            
            if b.quantity <= b.reorder_point:
                low_stock_items += 1
            
            items.append({
                "product_id": str(b.id),
                "name": b.name,
                "sku": b.sku,
                "category": b.category,
                "quantity": float(b.quantity),
                "average_cost": float(b.average_cost),
                "inventory_value": float(inventory_value),
                "reorder_point": float(b.reorder_point),
                "safety_stock": float(b.safety_stock),
                "status": "low" if b.quantity <= b.reorder_point else "ok"
            })
        
        return {
            "type": "inventory",
            "generated_at": datetime.now().isoformat(),
            "total_items": len(items),
            "total_inventory_value": float(total_inventory_value),
            "low_stock_items": low_stock_items,
            "items": items
        }
    
    @staticmethod
    def get_sales_report(business_id: str, days: int = 30, db: Session = None):
        """Generate sales report"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        sales = db.query(Sale).filter(
            Sale.business_id == business_id,
            Sale.sale_date >= cutoff_date,
            Sale.status == 'completed'
        ).all()
        
        total_sales = Decimal("0")
        total_quantity = Decimal("0")
        top_products = db.query(
            Product.name,
            Product.sku,
            func.sum(SaleItem.quantity).label('qty'),
            func.sum(SaleItem.line_total).label('revenue')
        ).join(SaleItem).join(Sale).filter(
            Sale.business_id == business_id,
            Sale.sale_date >= cutoff_date,
            Sale.status == 'completed'
        ).group_by(Product.name, Product.sku).order_by(
            func.sum(SaleItem.line_total).desc()
        ).limit(10).all()
        
        for sale in sales:
            total_sales += sale.total_amount
            for item in sale.items:
                total_quantity += item.quantity
        
        return {
            "type": "sales",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_sales": float(total_sales),
            "total_transactions": len(sales),
            "total_quantity_sold": float(total_quantity),
            "average_transaction": float(total_sales / len(sales)) if sales else 0,
            "top_products": [
                {
                    "name": p.name,
                    "sku": p.sku,
                    "quantity": float(p.qty or 0),
                    "revenue": float(p.revenue or 0)
                }
                for p in top_products
            ]
        }
    
    @staticmethod
    def get_stock_movement_report(business_id: str, days: int = 30, db: Session = None):
        """Generate stock movement report"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        movements = db.query(StockMovement).filter(
            StockMovement.business_id == business_id,
            StockMovement.created_at >= cutoff_date
        ).all()
        
        by_type = {}
        for movement in movements:
            if movement.movement_type not in by_type:
                by_type[movement.movement_type] = {
                    "count": 0,
                    "total_quantity": Decimal("0")
                }
            by_type[movement.movement_type]["count"] += 1
            by_type[movement.movement_type]["total_quantity"] += movement.quantity
        
        return {
            "type": "stock_movements",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_movements": len(movements),
            "by_type": {
                k: {
                    "count": v["count"],
                    "total_quantity": float(v["total_quantity"])
                }
                for k, v in by_type.items()
            }
        }
    
    @staticmethod
    def get_purchase_report(business_id: str, days: int = 30, db: Session = None):
        """Generate purchase report"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        purchases = db.query(Purchase).filter(
            Purchase.business_id == business_id,
            Purchase.purchase_date >= cutoff_date.date(),
            Purchase.status == 'received'
        ).all()
        
        total_spent = Decimal("0")
        total_items = Decimal("0")
        
        for purchase in purchases:
            total_spent += purchase.total_amount
            for item in purchase.items:
                total_items += item.quantity
        
        return {
            "type": "purchases",
            "period_days": days,
            "generated_at": datetime.now().isoformat(),
            "total_purchases": len(purchases),
            "total_amount": float(total_spent),
            "total_items_received": float(total_items),
            "average_purchase": float(total_spent / len(purchases)) if purchases else 0
        }