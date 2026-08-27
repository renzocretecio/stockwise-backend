from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel import Session, select
from fastapi import HTTPException, status
from sqlalchemy import func

from app.models.product import Product
from app.models.inventory import StockBalance, StockMovement, InventoryCount, InventoryCountItem
from app.schemas.inventory_count import InventoryCountCreate, CountScope, RecordCountItem
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
                status="in_progress",
                notes=payload.name,   # ← using notes as the session label, since there's no `name` column
                created_by=user_id,
            )
            db.add(count)
            db.flush()

            for product, stock_balance in rows:
                item = InventoryCountItem(
                    inventory_count=count,
                    product_id=product.id,
                    expected_quantity=stock_balance.quantity,
                    counted_quantity=None,
                )
                db.add(item)

            db.commit()
            db.refresh(count)

            return {
                "inventory_count_id": str(count.id),
                "name": payload.name,
                "status": count.status,
                "total_items": len(rows),
                "message": f"Count session '{payload.name}' started with {len(rows)} products",
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
    def record_count_items(
        business_id: str,
        count_id: str,
        items: list[RecordCountItem],
        user_id: str,
        db: Session,
    ) -> dict:
        """Record counted quantities for multiple products in a count session."""

        count = db.execute(
            select(InventoryCount).where(
                InventoryCount.business_id == business_id,
                InventoryCount.id == count_id,
            )
        ).scalar_one_or_none()

        if not count:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Count not found",
            )

        if count.status != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record items on a count with status '{count.status}'",
            )

        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No count items provided",
            )

        product_ids = [
            item.product_id
            for item in items
        ]

        count_items = db.execute(
            select(InventoryCountItem).where(
                InventoryCountItem.inventory_count_id == count_id,
                InventoryCountItem.product_id.in_(product_ids),
            )
        ).scalars().all()

        count_item_map = {
            str(item.product_id): item
            for item in count_items
        }

        missing_product_ids = [
            product_id
            for product_id in product_ids
            if product_id not in count_item_map
        ]

        if missing_product_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Some products are not part of this count session",
                    "product_ids": missing_product_ids,
                },
            )

        results = []

        for payload in items:
            item = count_item_map[payload.product_id]

            item.counted_quantity = payload.counted_quantity
            item.notes = payload.notes
            item.counted_at = func.now()

            variance = (
                item.counted_quantity -
                item.expected_quantity
            )

            results.append({
                "product_id": str(item.product_id),
                "expected_quantity": float(item.expected_quantity),
                "counted_quantity": float(item.counted_quantity),
                "variance": float(variance),
            })

        db.commit()

        return {
            "count_id": str(count.id),
            "updated_items": len(results),
            "items": results,
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
            .where(InventoryCountItem.inventory_count_id == count_id)
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
            "name": count.notes or f"Count — {count.count_date}",
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
                select(InventoryCountItem).where(InventoryCountItem.inventory_count_id == count.id)
            ).scalars().all()

            counted = sum(1 for i in items if i.counted_quantity is not None)

            result.append({
                "id": str(count.id),
                "name": count.notes or f"Count — {count.count_date}",
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

            if count.status != "in_progress":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Count already '{count.status}'",
                )

            items = db.execute(
                select(InventoryCountItem).where(InventoryCountItem.inventory_count_id == count_id)
            ).scalars().all()

            adjustments_made = 0

            for item in items:
                if item.counted_quantity is None:
                    continue

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
                    movement_type=MovementType.ADJUSTMENT.value,
                    quantity=variance,
                    reference_type="inventory_count",
                    reference_id=count.id,
                    reason="physical_count",
                    notes="Physical count variance",
                    created_by=user_id,
                )
                db.add(movement)
                adjustments_made += 1

            count.status = "finalized"
            count.finalized_by = user_id
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

        if count.status != "in_progress":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel a count with status '{count.status}'",
            )

        count.status = "cancelled"
        db.add(count)
        db.commit()

        return {"success": True, "message": "Count cancelled"}