from sqlmodel import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from sqlalchemy import func, or_, select

from app.models.product import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate


class SupplierService:
    @staticmethod
    def create_supplier(business_id: str, payload: SupplierCreate, db: Session) -> dict:
        """
        Create a new supplier.
        
        Args:
            business_id: Business ID
            payload: SupplierCreate schema
            db: Database session
            
        Returns:
            Supplier data dict
            
        Raises:
            HTTPException: If validation fails
        """
        try:
            # Validate name uniqueness within business
            existing = db.execute(
                select(Supplier).where(
                    Supplier.business_id == business_id,
                    Supplier.name == payload.name,
                    Supplier.is_active == True,
                )
            ).scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Supplier '{payload.name}' already exists",
                )

            supplier = Supplier(
                business_id=business_id,
                name=payload.name,
                contact_person=payload.contact_person,
                email=payload.email,
                phone=payload.phone,
                address=payload.address,
                payment_terms=payload.payment_terms,
                lead_time_days=payload.lead_time_days,
                notes=payload.notes,
                is_active=True,
            )

            db.add(supplier)
            db.commit()
            db.refresh(supplier)

            return SupplierService._format_supplier_response(supplier)

        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Supplier creation failed: Database constraint violation",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Supplier creation failed: {str(e)}",
            )

    @staticmethod
    def get_suppliers(business_id: str, db: Session) -> list:
        """Get all active suppliers for a business"""
        suppliers = db.execute(
            select(Supplier).where(
                Supplier.business_id == business_id,
                Supplier.is_active == True,
            ).order_by(Supplier.name)
        ).scalars().all()

        return suppliers

    @staticmethod
    def get_suppliers(
        business_id: str,
        db: Session,
        page: int = 1,
        page_size: int = 10,
        search: str | None = None,
    ):
        query = select(Supplier).where(
            Supplier.business_id == business_id,
            Supplier.is_active == True,
        )

        if search:
            search_term = f"%{search.strip()}%"

            query = query.where(
                or_(
                    Supplier.name.ilike(search_term),
                    Supplier.contact_person.ilike(search_term),
                    Supplier.email.ilike(search_term),
                    Supplier.phone.ilike(search_term),
                )
            )

        count_query = select(
            func.count()
        ).select_from(
            query.subquery()
        )

        total = db.execute(
            count_query
        ).scalar_one()

        suppliers = db.execute(
            query
            .order_by(Supplier.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).scalars().all()

        return suppliers, total

    @staticmethod
    def update_supplier(
        business_id: str, supplier_id: str, payload: SupplierUpdate, db: Session
    ) -> dict:
        """Update a supplier"""
        supplier = db.execute(
            select(Supplier).where(
                Supplier.business_id == business_id,
                Supplier.id == supplier_id,
            )
        ).scalar_one_or_none()

        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplier not found",
            )

        update_data = payload.model_dump(exclude_unset=True)

        # Check name uniqueness if changing name
        if "name" in update_data and update_data["name"] != supplier.name:
            existing = db.execute(
                select(Supplier).where(
                    Supplier.business_id == business_id,
                    Supplier.name == update_data["name"],
                    Supplier.is_active == True,
                    Supplier.id != supplier_id,
                )
            ).scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Supplier '{update_data['name']}' already exists",
                )

        for field, value in update_data.items():
            setattr(supplier, field, value)

        db.add(supplier)
        db.commit()
        db.refresh(supplier)

        return SupplierService._format_supplier_response(supplier)

    @staticmethod
    def soft_delete_supplier(business_id: str, supplier_id: str, db: Session) -> dict:
        """Soft delete a supplier"""
        supplier = db.execute(
            select(Supplier).where(
                Supplier.business_id == business_id,
                Supplier.id == supplier_id,
            )
        ).scalar_one_or_none()

        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplier not found",
            )

        supplier.is_active = False
        db.add(supplier)
        db.commit()

        return {"success": True, "message": "Supplier deleted"}

    @staticmethod
    def _format_supplier_response(supplier: Supplier) -> dict:
        """Format supplier response"""
        return {
            "id": str(supplier.id),
            "name": supplier.name,
            "contact_person": supplier.contact_person,
            "email": supplier.email,
            "phone": supplier.phone,
            "address": supplier.address,
            "payment_terms": supplier.payment_terms,
            "lead_time_days": supplier.lead_time_days,
            "notes": supplier.notes,
            "is_active": supplier.is_active,
        }