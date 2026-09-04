from decimal import Decimal
from sqlmodel import Session, select
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from datetime import datetime, timezone

from app.models.product import Product, Supplier
from app.models.purchase import Purchase, PurchaseItem
from app.models.inventory import StockBalance, StockMovement
from app.schemas.purchase import PurchaseCreate, PurchaseUpdate, PurchaseStatus
from app.schemas.stock import MovementType


class PurchaseService:
    @staticmethod
    def order_purchase(
        business_id: str,
        purchase_id: str,
        user_id: str,
        db: Session,
    ) -> dict:
        """Confirm a draft purchase without changing inventory."""
        try:
            purchase = db.execute(
                select(Purchase)
                .where(
                    Purchase.business_id == business_id,
                    Purchase.id == purchase_id,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if not purchase:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Purchase not found",
                )
            if purchase.status != PurchaseStatus.DRAFT.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot order a purchase with status '{purchase.status}'",
                )

            item_count = db.execute(
                select(func.count(PurchaseItem.id)).where(
                    PurchaseItem.purchase_id == purchase.id
                )
            ).scalar_one()
            if not item_count:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Purchase has no items to order",
                )

            purchase.status = PurchaseStatus.ORDERED.value
            purchase.ordered_at = datetime.now(timezone.utc)
            purchase.ordered_by = user_id
            db.add(purchase)
            db.commit()

            return {
                "purchase_id": str(purchase.id),
                "status": purchase.status,
                "message": "Purchase ordered and awaiting receipt",
            }
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to order purchase: {str(e)}",
            )

    @staticmethod
    def create_purchase(
        business_id: str,
        payload: PurchaseCreate,
        user_id: str,
        db: Session,
    ) -> dict:
        """Create a new purchase draft"""
        try:
            # Validate supplier
            supplier = db.execute(
                select(Supplier).where(
                    Supplier.business_id == business_id,
                    Supplier.id == payload.supplier_id,
                    Supplier.is_active == True,
                )
            ).scalar_one_or_none()

            if not supplier:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Supplier not found",
                )

            # Validate all products exist
            product_ids = [item.product_id for item in payload.items]
            products = db.execute(
                select(Product).where(
                    Product.business_id == business_id,
                    Product.id.in_(product_ids),
                    Product.is_active == True,
                )
            ).scalars().all()

            products_by_id = {str(p.id): p for p in products}
            missing = set(product_ids) - set(products_by_id.keys())
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Products not found: {', '.join(missing)}",
                )

            # Calculate totals
            subtotal = sum(
                item.quantity * item.unit_cost for item in payload.items
            )
            total_amount = subtotal + payload.tax_amount - payload.discount_amount

            if total_amount < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Discount cannot exceed subtotal + tax",
                )

            # Create purchase
            purchase = Purchase(
                business_id=business_id,
                supplier_id=payload.supplier_id,
                reference_number=payload.reference_number,
                expected_delivery_date=payload.expected_delivery_date,
                status=PurchaseStatus.DRAFT.value,
                subtotal=subtotal,
                tax_amount=payload.tax_amount,
                discount_amount=payload.discount_amount,
                total_amount=total_amount,
                notes=payload.notes,
                created_by=user_id,
            )
            db.add(purchase)
            db.flush()

            # Create purchase items
            for item in payload.items:
                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    line_total=item.quantity * item.unit_cost,
                )
                db.add(purchase_item)

            db.commit()
            db.refresh(purchase)

            return {
                "purchase_id": str(purchase.id),
                "status": purchase.status,
                "total_amount": float(purchase.total_amount),
                "message": f"Purchase draft created with {len(payload.items)} item(s)",
            }

        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Purchase creation failed: Database constraint violation",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Purchase creation failed: {str(e)}",
            )

    @staticmethod
    def get_purchase(
        business_id: str,
        purchase_id: str,
        db: Session,
    ) -> dict:
        """Get a single purchase with items."""

        purchase = db.execute(
            select(Purchase)
            .where(
                Purchase.business_id == business_id,
                Purchase.id == purchase_id,
            )
        ).scalar_one_or_none()

        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase not found",
            )

        return PurchaseService._format_purchase_response(
            purchase,
            db,
        )

    @staticmethod
    def get_purchases(
        business_id: str,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        supplier_id: str | None = None,
        search: str | None = None,
    ) -> dict:
        """Get paginated purchases for a business."""

        query = (
            select(Purchase)
            .outerjoin(Supplier, Purchase.supplier_id == Supplier.id)
            .where(Purchase.business_id == business_id)
        )

        if status_filter:
            query = query.where(
                Purchase.status == status_filter
            )

        if supplier_id:
            query = query.where(
                Purchase.supplier_id == supplier_id
            )

        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Purchase.reference_number.ilike(search_term),
                    Supplier.name.ilike(search_term),
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

        offset = (page - 1) * page_size

        query = (
            query
            .order_by(Purchase.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        purchases = db.execute(
            query
        ).scalars().all()

        items = []

        for purchase in purchases:
            supplier = db.execute(
                select(Supplier).where(
                    Supplier.id == purchase.supplier_id
                )
            ).scalar_one_or_none()

            purchase_items = db.execute(
                select(PurchaseItem).where(
                    PurchaseItem.purchase_id == purchase.id
                )
            ).scalars().all()

            formatted_items = []

            for purchase_item in purchase_items:
                product = db.execute(
                    select(Product).where(
                        Product.id == purchase_item.product_id
                    )
                ).scalar_one_or_none()

                formatted_items.append({
                    "id": str(purchase_item.id),
                    "product_id": str(purchase_item.product_id),
                    "product_name": product.name if product else "Unknown",
                    "sku": product.sku if product else None,
                    "quantity": float(purchase_item.quantity),
                    "unit_cost": float(purchase_item.unit_cost),
                    "line_total": float(
                        purchase_item.quantity *
                        purchase_item.unit_cost
                    ),
                })

            items.append({
                "id": str(purchase.id),
                "supplier_id": str(purchase.supplier_id),
                "supplier_name": supplier.name if supplier else "Unknown",
                "reference_number": purchase.reference_number,
                "status": purchase.status,
                "expected_delivery_date": (
                    purchase.expected_delivery_date
                ),
                "total_amount": float(purchase.total_amount),
                "item_count": len(formatted_items),
                "items": formatted_items,
                "created_at": purchase.created_at,
                "ordered_at": purchase.ordered_at,
                "received_at": purchase.received_at,
            })

        total_pages = (
            (total + page_size - 1) // page_size
            if total > 0
            else 0
        )

        return {
            "purchases": items,
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
    def update_purchase(
        business_id: str,
        purchase_id: str,
        payload: PurchaseUpdate,
        db: Session,
    ) -> dict:
        """Update a draft purchase (only allowed before receiving)"""
        purchase = db.execute(
            select(Purchase).where(
                Purchase.business_id == business_id,
                Purchase.id == purchase_id,
            )
        ).scalar_one_or_none()

        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase not found",
            )

        if purchase.status != PurchaseStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update a purchase with status '{purchase.status}'",
            )

        update_data = payload.model_dump(exclude_unset=True)

        # Handle item replacement separately
        items = update_data.pop("items", None)

        if "supplier_id" in update_data:
            supplier = db.execute(
                select(Supplier).where(
                    Supplier.business_id == business_id,
                    Supplier.id == update_data["supplier_id"],
                    Supplier.is_active == True,
                )
            ).scalar_one_or_none()
            if not supplier:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Supplier not found",
                )

        for field, value in update_data.items():
            setattr(purchase, field, value)

        if items is not None:
            # Delete old items
            db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
            )
            existing_items = db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
            ).scalars().all()
            for old_item in existing_items:
                db.delete(old_item)
            db.flush()

            # Validate products
            product_ids = [item["product_id"] for item in items]
            products = db.execute(
                select(Product).where(
                    Product.business_id == business_id,
                    Product.id.in_(product_ids),
                    Product.is_active == True,
                )
            ).scalars().all()

            products_by_id = {str(p.id): p for p in products}
            missing = set(product_ids) - set(products_by_id.keys())
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Products not found: {', '.join(missing)}",
                )

            subtotal = Decimal("0")
            for item in items:
                line_total = Decimal(str(item["quantity"])) * Decimal(str(item["unit_cost"]))
                subtotal += line_total
                purchase_item = PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    unit_cost=item["unit_cost"],
                    line_total=line_total,
                )
                db.add(purchase_item)

            purchase.subtotal = subtotal
            purchase.total_amount = subtotal + purchase.tax_amount - purchase.discount_amount

        db.add(purchase)
        db.commit()
        db.refresh(purchase)

        return PurchaseService._format_purchase_response(purchase, db)

    @staticmethod
    def receive_purchase(
        business_id: str,
        purchase_id: str,
        user_id: str,
        db: Session,
    ) -> dict:
        """Receive a purchase — updates stock balances and creates movements"""
        try:
            purchase = db.execute(
                select(Purchase)
                .where(
                    Purchase.business_id == business_id,
                    Purchase.id == purchase_id,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if not purchase:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Purchase not found",
                )

            if purchase.status != PurchaseStatus.ORDERED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot receive a purchase with status '{purchase.status}'",
                )

            items = db.execute(
                select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id)
            ).scalars().all()

            if not items:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Purchase has no items to receive",
                )

            items_received = 0

            for item in items:
                stock_balance = db.execute(
                    select(StockBalance).where(
                        StockBalance.business_id == business_id,
                        StockBalance.product_id == item.product_id,
                    )
                ).scalar_one_or_none()

                if not stock_balance:
                    # Create if it doesn't exist for some reason
                    stock_balance = StockBalance(
                        business_id=business_id,
                        product_id=item.product_id,
                        quantity=Decimal("0"),
                        reserved_quantity=Decimal("0"),
                        average_cost=Decimal("0"),
                    )
                    db.add(stock_balance)
                    db.flush()

                # Weighted average cost recalculation
                old_quantity = stock_balance.quantity
                old_cost = stock_balance.average_cost
                new_quantity = old_quantity + item.quantity

                if new_quantity > 0:
                    new_average_cost = (
                        (old_quantity * old_cost) + (item.quantity * item.unit_cost)
                    ) / new_quantity
                else:
                    new_average_cost = item.unit_cost

                stock_balance.quantity = new_quantity
                stock_balance.average_cost = new_average_cost
                db.add(stock_balance)

                movement = StockMovement(
                    business_id=business_id,
                    product_id=item.product_id,
                    movement_type=MovementType.PURCHASE.value,
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    reference_type="purchase",
                    reference_id=purchase.id,
                    notes=f"Received from purchase {purchase.reference_number or purchase.id}",
                    created_by=user_id,
                )
                db.add(movement)

                # Also update product cost_price to reflect latest cost (optional business rule)
                product = db.execute(
                    select(Product).where(Product.id == item.product_id)
                ).scalar_one_or_none()
                if product:
                    product.cost_price = item.unit_cost
                    db.add(product)

                items_received += 1

            purchase.status = PurchaseStatus.RECEIVED.value
            purchase.received_at = datetime.now(timezone.utc)
            purchase.received_by = user_id
            db.add(purchase)

            db.commit()

            return {
                "purchase_id": str(purchase.id),
                "status": purchase.status,
                "items_received": items_received,
                "message": f"Purchase received — {items_received} item(s) added to stock",
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to receive purchase: {str(e)}",
            )

    @staticmethod
    def cancel_purchase(business_id: str, purchase_id: str, db: Session) -> dict:
        """Cancel a draft purchase"""
        purchase = db.execute(
            select(Purchase)
            .where(
                Purchase.business_id == business_id,
                Purchase.id == purchase_id,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase not found",
            )

        if purchase.status != PurchaseStatus.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel a purchase with status '{purchase.status}'",
            )

        purchase.status = PurchaseStatus.CANCELLED.value
        db.add(purchase)
        db.commit()

        return {
            "purchase_id": str(purchase.id),
            "status": purchase.status,
            "message": "Purchase cancelled",
        }

    @staticmethod
    def _format_purchase_response(purchase: Purchase, db: Session) -> dict:
        """Format purchase response with items and supplier info"""
        supplier = db.execute(
            select(Supplier).where(Supplier.id == purchase.supplier_id)
        ).scalar_one_or_none()

        rows = db.execute(
            select(PurchaseItem, Product)
            .join(Product, Product.id == PurchaseItem.product_id)
            .where(PurchaseItem.purchase_id == purchase.id)
        ).all()

        items = [
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "product_name": product.name,
                "sku": product.sku,
                "quantity": float(item.quantity),
                "unit_cost": float(item.unit_cost),
                "line_total": float(item.line_total),
            }
            for item, product in rows
        ]

        return {
            "id": str(purchase.id),
            "supplier_id": str(purchase.supplier_id),
            "supplier_name": supplier.name if supplier else "Unknown",
            "reference_number": purchase.reference_number,
            "status": purchase.status,
            "expected_delivery_date": purchase.expected_delivery_date,
            "items": items,
            "subtotal": float(purchase.subtotal),
            "tax_amount": float(purchase.tax_amount),
            "discount_amount": float(purchase.discount_amount),
            "total_amount": float(purchase.total_amount),
            "notes": purchase.notes,
            "created_by": str(purchase.created_by) if purchase.created_by else None,
            "created_at": purchase.created_at,
            "ordered_at": purchase.ordered_at,
            "received_at": purchase.received_at,
        }
