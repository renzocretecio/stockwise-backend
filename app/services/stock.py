from decimal import Decimal
from sqlmodel import Session, select
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.product import Product
from app.models.inventory import StockBalance, StockMovement
from app.schemas.stock import StockAdjustmentCreate, MovementType


class StockService:
    @staticmethod
    def get_stock_overview(
        business_id: str,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        status_filter: str | None = None,
    ) -> dict:
        """Get paginated stock overview with summary stats"""

        query = (
            select(StockBalance, Product)
            .join(Product, Product.id == StockBalance.product_id)
            .where(
                StockBalance.business_id == business_id,
                Product.is_active == True,
            )
        )

        if search:
            search_term = f"%{search.lower()}%"
            query = query.where(
                (Product.normalized_name.ilike(search_term))
                | (Product.sku.ilike(search_term))
            )

        # Fetch all matching rows first (for summary + status filter, since status is computed)
        all_rows = db.execute(query).all()

        items = []
        low_stock_count = 0
        out_of_stock_count = 0
        total_stock_value = Decimal("0")

        for stock_balance, product in all_rows:
            available = stock_balance.quantity - stock_balance.reserved_quantity
            stock_value = stock_balance.quantity * stock_balance.average_cost
            total_stock_value += stock_value

            if stock_balance.quantity <= 0:
                item_status = "out_of_stock"
                out_of_stock_count += 1
            elif stock_balance.quantity <= product.reorder_point:
                item_status = "low_stock"
                low_stock_count += 1
            else:
                item_status = "in_stock"

            if status_filter and status_filter != item_status:
                continue

            items.append({
                "product_id": str(product.id),
                "product_name": product.name,
                "sku": product.sku,
                "unit": product.unit,
                "quantity": float(stock_balance.quantity),
                "reserved_quantity": float(stock_balance.reserved_quantity),
                "available_quantity": float(available),
                "average_cost": float(stock_balance.average_cost),
                "stock_value": float(stock_value),
                "reorder_point": float(product.reorder_point),
                "safety_stock": float(product.safety_stock),
                "status": item_status,
            })

        total = len(items)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        # Paginate in-memory (status is computed, can't paginate at DB level easily)
        offset = (page - 1) * page_size
        paginated_items = items[offset : offset + page_size]

        return {
            "items": paginated_items,
            "summary": {
                "total_products": len(all_rows),
                "total_stock_value": float(total_stock_value),
                "low_stock_count": low_stock_count,
                "out_of_stock_count": out_of_stock_count,
            },
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
        }

    @staticmethod
    def get_stock_movements(
        business_id: str,
        db: Session,
        product_id: str | None = None,
        movement_type: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Get paginated stock movement history"""

        query = (
            select(StockMovement, Product)
            .join(Product, Product.id == StockMovement.product_id)
            .where(StockMovement.business_id == business_id)
        )

        if product_id:
            query = query.where(StockMovement.product_id == product_id)

        if movement_type:
            query = query.where(StockMovement.movement_type == movement_type)

        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar_one()

        offset = (page - 1) * page_size
        query = query.order_by(StockMovement.created_at.desc()).offset(offset).limit(page_size)

        rows = db.execute(query).all()

        movements = [
            {
                "id": str(movement.id),
                "product_id": str(movement.product_id),
                "product_name": product.name,
                "movement_type": movement.movement_type,
                "quantity_change": float(movement.quantity_change),
                "balance_after": float(movement.balance_after),
                "reference_type": movement.reference_type,
                "reference_id": str(movement.reference_id) if movement.reference_id else None,
                "notes": movement.notes,
                "created_by": str(movement.created_by) if movement.created_by else None,
                "created_at": movement.created_at,
            }
            for movement, product in rows
        ]

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "movements": movements,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1,
            },
        }

    @staticmethod
    def adjust_stock(
        business_id: str,
        payload: StockAdjustmentCreate,
        user_id: str,
        db: Session,
    ) -> dict:
        """Manually adjust stock quantity"""
        try:
            product = db.execute(
                select(Product).where(
                    Product.business_id == business_id,
                    Product.id == payload.product_id,
                    Product.is_active == True,
                )
            ).scalar_one_or_none()

            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product not found",
                )

            stock_balance = db.execute(
                select(StockBalance).where(
                    StockBalance.business_id == business_id,
                    StockBalance.product_id == payload.product_id,
                )
            ).scalar_one_or_none()

            if not stock_balance:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Stock balance not found",
                )

            quantity_before = stock_balance.quantity
            quantity_after = quantity_before + payload.quantity_change

            if quantity_after < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Adjustment would result in negative stock ({quantity_after})",
                )

            stock_balance.quantity = quantity_after
            db.add(stock_balance)

            movement = StockMovement(
                business_id=business_id,
                product_id=payload.product_id,
                movement_type=MovementType.ADJUSTMENT.value,
                quantity_change=payload.quantity_change,
                balance_after=quantity_after,
                reference_type="adjustment",
                reference_id=None,
                notes=f"[{payload.reason.value}] {payload.notes or ''}".strip(),
                created_by=user_id,
            )
            db.add(movement)

            db.commit()
            db.refresh(stock_balance)

            return {
                "product_id": str(product.id),
                "quantity_before": float(quantity_before),
                "quantity_after": float(quantity_after),
                "quantity_change": float(payload.quantity_change),
                "message": f"Stock adjusted successfully for '{product.name}'",
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Stock adjustment failed: {str(e)}",
            )