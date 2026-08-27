from decimal import Decimal, ROUND_HALF_UP
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from datetime import datetime, timezone

from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem
from app.models.inventory import StockBalance, StockMovement
from app.schemas.sale import SaleCreate, SaleReturnCreate, SaleStatus
from app.schemas.stock import MovementType


class SaleService:
    @staticmethod
    def get_returns(
        business_id: str,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict:
        """Get paginated return history with original sale references and totals."""
        query = (
            select(SaleReturn, Sale.reference_number)
            .join(Sale, Sale.id == SaleReturn.sale_id)
            .where(SaleReturn.business_id == business_id)
        )

        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                Sale.reference_number.ilike(pattern)
                | SaleReturn.reason.ilike(pattern)
            )

        total = db.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar_one()
        rows = db.execute(
            query.order_by(SaleReturn.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        returns = []
        for sale_return, reference_number in rows:
            item_summary = db.execute(
                select(
                    func.count(SaleReturnItem.id),
                    func.coalesce(func.sum(SaleReturnItem.quantity), 0),
                ).where(SaleReturnItem.return_id == sale_return.id)
            ).one()
            returns.append({
                "id": str(sale_return.id),
                "sale_id": str(sale_return.sale_id),
                "sale_reference_number": reference_number,
                "status": sale_return.status,
                "reason": sale_return.reason,
                "notes": sale_return.notes,
                "refund_amount": float(sale_return.refund_amount),
                "item_count": item_summary[0],
                "total_quantity": float(item_summary[1]),
                "created_by": str(sale_return.created_by) if sale_return.created_by else None,
                "created_at": sale_return.created_at,
            })

        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "returns": returns,
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
    def create_return(
        business_id: str,
        sale_id: str,
        payload: SaleReturnCreate,
        user_id: str,
        db: Session,
    ) -> dict:
        """Create a partial/full return, restore stock, and record movements atomically."""
        try:
            # Locking the sale serializes returns for the same sale on databases
            # that support SELECT ... FOR UPDATE (including PostgreSQL).
            sale = db.execute(
                select(Sale)
                .where(Sale.business_id == business_id, Sale.id == sale_id)
                .with_for_update()
            ).scalar_one_or_none()

            if not sale:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sale not found")

            returnable_statuses = {
                SaleStatus.COMPLETED.value,
                SaleStatus.PARTIALLY_RETURNED.value,
            }
            if sale.status not in returnable_statuses:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot return a sale with status '{sale.status}'",
                )

            sale_items = db.execute(
                select(SaleItem).where(SaleItem.sale_id == sale.id)
            ).scalars().all()
            sale_items_by_id = {str(item.id): item for item in sale_items}

            requested_ids = {item.sale_item_id for item in payload.items}
            missing_ids = requested_ids - set(sale_items_by_id)
            if missing_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Sale items do not belong to this sale: {', '.join(sorted(missing_ids))}",
                )

            returned_rows = db.execute(
                select(
                    SaleReturnItem.sale_item_id,
                    func.coalesce(func.sum(SaleReturnItem.quantity), 0),
                )
                .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
                .where(
                    SaleReturn.sale_id == sale.id,
                    SaleReturn.status == "completed",
                )
                .group_by(SaleReturnItem.sale_item_id)
            ).all()
            already_returned = {str(item_id): Decimal(quantity) for item_id, quantity in returned_rows}

            for requested in payload.items:
                original = sale_items_by_id[requested.sale_item_id]
                remaining = Decimal(original.quantity) - already_returned.get(requested.sale_item_id, Decimal("0"))
                if requested.quantity > remaining:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Return quantity for sale item {requested.sale_item_id} exceeds "
                            f"remaining returnable quantity {remaining}"
                        ),
                    )

            sale_return = SaleReturn(
                business_id=business_id,
                sale_id=sale.id,
                status="completed",
                reason=payload.reason,
                notes=payload.notes,
                refund_amount=Decimal("0"),
                created_by=user_id,
            )
            db.add(sale_return)
            db.flush()

            refund_total = Decimal("0")
            for requested in payload.items:
                original = sale_items_by_id[requested.sale_item_id]
                refund_amount = (
                    Decimal(original.line_total) * requested.quantity / Decimal(original.quantity)
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                refund_total += refund_amount

                db.add(SaleReturnItem(
                    return_id=sale_return.id,
                    sale_item_id=original.id,
                    product_id=original.product_id,
                    quantity=requested.quantity,
                    unit_price=original.unit_price,
                    unit_cost=original.unit_cost,
                    refund_amount=refund_amount,
                ))

                stock_balance = db.execute(
                    select(StockBalance)
                    .where(
                        StockBalance.business_id == business_id,
                        StockBalance.product_id == original.product_id,
                    )
                    .with_for_update()
                ).scalar_one_or_none()
                if not stock_balance:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Stock balance missing for product {original.product_id}",
                    )

                stock_balance.quantity += requested.quantity
                db.add(stock_balance)
                db.add(StockMovement(
                    business_id=business_id,
                    product_id=original.product_id,
                    movement_type=MovementType.RETURN.value,
                    quantity=requested.quantity,
                    unit_cost=original.unit_cost,
                    reference_type="return",
                    reference_id=sale_return.id,
                    reason=payload.reason,
                    notes=payload.notes,
                    created_by=user_id,
                ))

            sale_return.refund_amount = refund_total

            requested_by_id = {item.sale_item_id: item.quantity for item in payload.items}
            fully_returned = all(
                already_returned.get(str(item.id), Decimal("0"))
                + requested_by_id.get(str(item.id), Decimal("0"))
                == Decimal(item.quantity)
                for item in sale_items
            )
            sale.status = (
                SaleStatus.RETURNED.value if fully_returned
                else SaleStatus.PARTIALLY_RETURNED.value
            )
            db.add(sale)
            db.commit()

            return {
                "return_id": str(sale_return.id),
                "sale_id": str(sale.id),
                "sale_status": sale.status,
                "refund_amount": float(refund_total),
                "message": "Return completed and stock restored",
            }
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Return creation failed: Database constraint violation",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Return creation failed: {str(e)}",
            )

    @staticmethod
    def create_sale(
        business_id: str,
        payload: SaleCreate,
        user_id: str,
        db: Session,
    ) -> dict:
        """Create a new sale — validates stock, deducts inventory, records movements"""
        try:
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

            # Validate stock availability BEFORE making any changes
            stock_balances = {}
            insufficient_stock = []

            for item in payload.items:
                stock_balance = db.execute(
                    select(StockBalance).where(
                        StockBalance.business_id == business_id,
                        StockBalance.product_id == item.product_id,
                    )
                ).scalar_one_or_none()

                if not stock_balance:
                    insufficient_stock.append(
                        f"{products_by_id[item.product_id].name}: no stock record"
                    )
                    continue

                available = stock_balance.quantity - stock_balance.reserved_quantity

                if available < item.quantity:
                    insufficient_stock.append(
                        f"{products_by_id[item.product_id].name}: "
                        f"requested {item.quantity}, available {available}"
                    )
                    continue

                stock_balances[item.product_id] = stock_balance

            if insufficient_stock:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock: {'; '.join(insufficient_stock)}",
                )

            # Calculate totals
            subtotal = sum(item.quantity * item.unit_price for item in payload.items)
            total_amount = subtotal + payload.tax_amount - payload.discount_amount

            if total_amount < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Discount cannot exceed subtotal + tax",
                )

            # Create sale
            sale = Sale(
                business_id=business_id,
                reference_number=payload.reference_number,
                status=SaleStatus.COMPLETED.value,
                payment_method=payload.payment_method.value,
                subtotal=subtotal,
                tax_amount=payload.tax_amount,
                discount_amount=payload.discount_amount,
                total_amount=total_amount,
                notes=payload.notes,
                created_by=user_id,
            )
            db.add(sale)
            db.flush()

            # Create sale items, deduct stock, create movements
            for item in payload.items:
                product = products_by_id[item.product_id]
                stock_balance = stock_balances[item.product_id]

                line_total = item.quantity * item.unit_price

                sale_item = SaleItem(
                    sale_id=sale.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    unit_cost=product.cost_price,
                    line_total=line_total,
                )
                db.add(sale_item)

                new_quantity = stock_balance.quantity - item.quantity
                stock_balance.quantity = new_quantity
                db.add(stock_balance)

                movement = StockMovement(
                    business_id=business_id,
                    product_id=item.product_id,
                    movement_type=MovementType.SALE.value,
                    quantity=-item.quantity,               # ← was quantity_change
                    unit_cost=product.cost_price,
                    reference_type="sale",
                    reference_id=sale.id,
                    notes=f"Sold via {payload.reference_number or sale.id}",
                    created_by=user_id,
                )
                db.add(movement)

            db.commit()
            db.refresh(sale)

            return {
                "sale_id": str(sale.id),
                "status": sale.status,
                "total_amount": float(sale.total_amount),
                "message": f"Sale completed — {len(payload.items)} item(s) sold",
            }

        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sale creation failed: Database constraint violation",
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Sale creation failed: {str(e)}",
            )

    @staticmethod
    def get_sale(business_id: str, sale_id: str, db: Session) -> dict:
        """Get a single sale with items"""
        sale = db.execute(
            select(Sale).where(
                Sale.business_id == business_id,
                Sale.id == sale_id,
            )
        ).scalar_one_or_none()

        if not sale:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sale not found",
            )

        return SaleService._format_sale_response(sale, db)

    @staticmethod
    def get_sales(
        business_id: str,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        payment_method: str | None = None,
    ) -> dict:
        """Get paginated sales for a business"""
        query = select(Sale).where(Sale.business_id == business_id)

        if status_filter:
            query = query.where(Sale.status == status_filter)

        if payment_method:
            query = query.where(Sale.payment_method == payment_method)

        count_query = select(func.count()).select_from(query.subquery())
        total = db.execute(count_query).scalar_one()

        offset = (page - 1) * page_size
        query = query.order_by(Sale.created_at.desc()).offset(offset).limit(page_size)

        sales = db.execute(query).scalars().all()

        items = []
        for sale in sales:
            item_count = db.execute(
                select(func.count()).select_from(SaleItem).where(
                    SaleItem.sale_id == sale.id
                )
            ).scalar_one()

            items.append({
                "id": str(sale.id),
                "reference_number": sale.reference_number,
                "status": sale.status,
                "payment_method": sale.payment_method,
                "total_amount": float(sale.total_amount),
                "item_count": item_count,
                "created_at": sale.created_at,
            })

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "sales": items,
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
    def void_sale(
        business_id: str,
        sale_id: str,
        reason: str,
        user_id: str,
        db: Session,
    ) -> dict:
        """Void a sale — reverses stock deduction"""
        try:
            sale = db.execute(
                select(Sale)
                .where(
                    Sale.business_id == business_id,
                    Sale.id == sale_id,
                )
                .with_for_update()
            ).scalar_one_or_none()

            if not sale:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Sale not found",
                )

            if sale.status != SaleStatus.COMPLETED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot void a sale with status '{sale.status}'",
                )

            items = db.execute(
                select(SaleItem).where(SaleItem.sale_id == sale.id)
            ).scalars().all()

            for item in items:
                stock_balance = db.execute(
                    select(StockBalance)
                    .where(
                        StockBalance.business_id == business_id,
                        StockBalance.product_id == item.product_id,
                    )
                    .with_for_update()
                ).scalar_one_or_none()

                if not stock_balance:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Stock balance missing for product {item.product_id}",
                    )

                new_quantity = stock_balance.quantity + item.quantity
                stock_balance.quantity = new_quantity
                db.add(stock_balance)

                movement = StockMovement(
                        business_id=business_id,
                        product_id=item.product_id,
                        movement_type=MovementType.RETURN.value,
                        quantity=item.quantity,                # ← was quantity_change
                        unit_cost=item.unit_cost,
                        reference_type="sale_void",
                        reference_id=sale.id,
                        reason="void",
                        notes=reason,
                        created_by=user_id,
                )
                db.add(movement)

            sale.status = SaleStatus.VOIDED.value
            sale.voided_at = datetime.now(timezone.utc)
            sale.void_reason = reason
            sale.voided_by = user_id
            db.add(sale)

            db.commit()

            return {
                "sale_id": str(sale.id),
                "status": sale.status,
                "message": "Sale voided and stock restored",
            }

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to void sale: {str(e)}",
            )

    @staticmethod
    def _format_sale_response(sale: Sale, db: Session) -> dict:
        """Format sale response with items"""
        rows = db.execute(
            select(SaleItem, Product)
            .join(Product, Product.id == SaleItem.product_id)
            .where(SaleItem.sale_id == sale.id)
        ).all()

        items = []
        for item, product in rows:
            returned_quantity = db.execute(
                select(func.coalesce(func.sum(SaleReturnItem.quantity), 0))
                .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
                .where(
                    SaleReturnItem.sale_item_id == item.id,
                    SaleReturn.status == "completed",
                )
            ).scalar_one()
            returned_quantity = Decimal(returned_quantity)
            items.append({
                "id": str(item.id),
                "product_id": str(item.product_id),
                "product_name": product.name,
                "sku": product.sku,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "unit_cost": float(item.unit_cost),
                "line_total": float(item.line_total),
                "line_profit": float((item.unit_price - item.unit_cost) * item.quantity),
                "returned_quantity": float(returned_quantity),
                "returnable_quantity": float(Decimal(item.quantity) - returned_quantity),
            })

        total_profit = sum(Decimal(str(item["line_profit"])) for item in items)

        return {
            "id": str(sale.id),
            "reference_number": sale.reference_number,
            "status": sale.status,
            "payment_method": sale.payment_method,
            "items": items,
            "subtotal": float(sale.subtotal),
            "tax_amount": float(sale.tax_amount),
            "discount_amount": float(sale.discount_amount),
            "total_amount": float(sale.total_amount),
            "total_profit": float(total_profit),
            "notes": sale.notes,
            "created_by": str(sale.created_by) if sale.created_by else None,
            "created_at": sale.created_at,
            "voided_at": sale.voided_at,
            "void_reason": sale.void_reason,
        }
