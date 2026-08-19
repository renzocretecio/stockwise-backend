from decimal import Decimal
from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.models.product import Product
from app.models.inventory import StockBalance, StockMovement, InventoryCount, InventoryCountItem
from app.schemas.inventory_count import InventoryCountCreate, CountScope, CountStatus
from app.schemas.stock import MovementType


class InventoryCountService:
    @staticmethod
    def create_count(
        business_id: str,
        payload: InventoryCountCreate,
        user_id: str,
        db: Session,
    ) -> dict:
        """Start a new physical count session"""
        try:
            query = select(Product, StockBalance).join(
                StockBalance, StockBalance.product_id == Product.id
            ).where(
                Product.business_id == business_id,
                Product.is_active == True,
            )

            if payload.scope == CountScope.CATEGORY and payload.category:
                query = query.where(Product.category == payload.category)
            elif payload.scope == CountScope.CUSTOM and payload.product_ids:
                query = query.where(Product.id.in_(payload.product_ids))

            rows = db.execute(query).all()

            if not rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No products found for the given scope",
                )

            count = InventoryCount(
                business_id=business_id,
                name=payload.name,
                status=CountStatus.IN_PROGRESS.value,
                created_by=user_id,
            )
            db.add(count)
            db.flush()

            for product, stock_balance in rows:
                item = InventoryCountItem(
                    count_id=count.id,
                    product_id=product.id,
                    expected_quantity=stock_balance.quantity,
                    counted_quantity=None,
                )
                db.add(item)

            db.commit()
            db.refresh(count)

            return {
                "count_id": str(count.id),
                "name": count.name,
                "status": count.status,
                "total_items": len(rows),
                "message": f"Count session '{count.name}' started with {len(rows)} products",
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to start count: {str(e)}",
            )

    @staticmethod
    def record_count_item(
        business_id: str,
        count_id: str,
        product_id: str,
        counted_quantity: Decimal,
        notes: str | None,
        user_id: str,
        db: Session,
    ) -> dict:
        """Record a counted quantity for a product in the session"""
        count = db.execute(
            select(InventoryCount).where(
                InventoryCount.business_id == business_id,
                InventoryCount.id == count_id,
            )
        ).scalar_one_or_none()

        if not count:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count not found")

        if count.status != CountStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record items on a count with status '{count.status}'",
            )

        item = db.execute(
            select(InventoryCountItem).where(
                InventoryCountItem.count_id == count_id,
                InventoryCountItem.product_id == product_id,
            )
        ).scalar_one_or_none()

        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not part of this count session",
            )

        item.counted_quantity = counted_quantity
        item.notes = notes
        item.counted_by = user_id
        db.add(item)
        db.commit()
        db.refresh(item)

        variance = item.counted_quantity - item.expected_quantity

        return {
            "product_id": str(product_id),
            "expected_quantity": float(item.expected_quantity),
            "counted_quantity": float(item.counted_quantity),
            "variance": float(variance),
        }

    @staticmethod
    def get_count_detail(business_id: str, count_id: str, db: Session) -> dict:
        """Get a count session with all items and their variances"""
        count = db.execute(
            select(InventoryCount).where(
                InventoryCount.business_id == business_id,
                InventoryCount.id == count_id,
            )
        ).scalar_one_or_none()

        if not count:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count not found")

        rows = db.execute(
            select(InventoryCountItem, Product)
            .join(Product, Product.id == InventoryCountItem.product_id)
            .where(InventoryCountItem.count_id == count_id)
        ).all()

        items = []
        counted_items = 0
        items_with_variance = 0

        for item, product in rows:
            variance = None
            if item.counted_quantity is not None:
                counted_items += 1
                variance = item.counted_quantity - item.expected_quantity
                if variance != 0:
                    items_with_variance += 1

            items.append({
                "product_id": str(product.id),
                "product_name": product.name,
                "sku": product.sku,
                "expected_quantity": float(item.expected_quantity),
                "counted_quantity": float(item.counted_quantity) if item.counted_quantity is not None else None,
                "variance": float(variance) if variance is not None else None,
            })

        return {
            "id": str(count.id),
            "name": count.name,
            "status": count.status,
            "scope": "custom",
            "total_items": len(rows),
            "counted_items": counted_items,
            "items_with_variance": items_with_variance,
            "created_at": count.created_at,
            "finalized_at": count.finalized_at,
            "items": items,
        }

    @staticmethod
    def get_counts(business_id: str, db: Session) -> list:
        """List all count sessions for a business"""
        counts = db.execute(
            select(InventoryCount)
            .where(InventoryCount.business_id == business_id)
            .order_by(InventoryCount.created_at.desc())
        ).scalars().all()

        result = []
        for count in counts:
            items = db.execute(
                select(InventoryCountItem).where(InventoryCountItem.count_id == count.id)
            ).scalars().all()

            counted = sum(1 for i in items if i.counted_quantity is not None)

            result.append({
                "id": str(count.id),
                "name": count.name,
                "status": count.status,
                "total_items": len(items),
                "counted_items": counted,
                "created_at": count.created_at,
                "finalized_at": count.finalized_at,
            })

        return result

    @staticmethod
    def finalize_count(business_id: str, count_id: str, user_id: str, db: Session) -> dict:
        """Finalize the count, applying variances as stock movements"""
        try:
            count = db.execute(
                select(InventoryCount).where(
                    InventoryCount.business_id == business_id,
                    InventoryCount.id == count_id,
                )
            ).scalar_one_or_none()

            if not count:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count not found")

            if count.status != CountStatus.IN_PROGRESS.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Count already '{count.status}'",
                )

            items = db.execute(
                select(InventoryCountItem).where(InventoryCountItem.count_id == count_id)
            ).scalars().all()

            adjustments_made = 0

            for item in items:
                if item.counted_quantity is None:
                    continue  # skip uncounted items

                variance = item.counted_quantity - item.expected_quantity
                if variance == 0:
                    continue

                stock_balance = db.execute(
                    select(StockBalance).where(
                        StockBalance.business_id == business_id,
                        StockBalance.product_id == item.product_id,
                    )
                ).scalar_one_or_none()

                if not stock_balance:
                    continue

                stock_balance.quantity = item.counted_quantity
                db.add(stock_balance)

                movement = StockMovement(
                    business_id=business_id,
                    product_id=item.product_id,
                    movement_type=MovementType.COUNT_ADJUSTMENT.value,
                    quantity_change=variance,
                    balance_after=item.counted_quantity,
                    reference_type="inventory_count",
                    reference_id=count.id,
                    notes=f"Physical count variance: {item.notes or ''}".strip(),
                    created_by=user_id,
                )
                db.add(movement)
                adjustments_made += 1

            count.status = CountStatus.COMPLETED.value
            count.finalized_by = user_id
            from datetime import datetime, timezone
            count.finalized_at = datetime.now(timezone.utc)
            db.add(count)

            db.commit()

            return {
                "count_id": str(count.id),
                "status": count.status,
                "adjustments_made": adjustments_made,
                "message": f"Count finalized with {adjustments_made} stock adjustment(s) applied",
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to finalize count: {str(e)}",
            )

    @staticmethod
    def cancel_count(business_id: str, count_id: str, db: Session) -> dict:
        """Cancel an in-progress count"""
        count = db.execute(
            select(InventoryCount).where(
                InventoryCount.business_id == business_id,
                InventoryCount.id == count_id,
            )
        ).scalar_one_or_none()

        if not count:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Count not found")

        if count.status != CountStatus.IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel a count with status '{count.status}'",
            )

        count.status = CountStatus.CANCELLED.value
        db.add(count)
        db.commit()

        return {"success": True, "message": "Count cancelled"}