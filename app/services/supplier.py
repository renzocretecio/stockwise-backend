from sqlalchemy.orm import Session
from app.models import Supplier

class SupplierService:
    @staticmethod
    def create_supplier(business_id: str, data: dict, db: Session):
        """Create a new supplier"""
        supplier = Supplier(
            business_id=business_id,
            name=data.get("name"),
            contact_person=data.get("contact_person"),
            email=data.get("email"),
            phone=data.get("phone"),
            address=data.get("address"),
            payment_terms=data.get("payment_terms"),
            lead_time_days=data.get("lead_time_days", 3),
            notes=data.get("notes")
        )
        db.add(supplier)
        db.commit()
        db.refresh(supplier)
        return supplier
    
    @staticmethod
    def get_suppliers(business_id: str, db: Session):
        """Get all suppliers for a business"""
        return db.query(Supplier).filter(
            Supplier.business_id == business_id,
            Supplier.is_active == True
        ).all()
    
    @staticmethod
    def get_supplier(business_id: str, supplier_id: str, db: Session):
        """Get supplier by ID"""
        return db.query(Supplier).filter(
            Supplier.business_id == business_id,
            Supplier.id == supplier_id
        ).first()