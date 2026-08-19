from decimal import Decimal
from sqlmodel import Session, select
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from datetime import datetime, timezone

from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.inventory import StockBalance, StockMovement
from app.schemas.sale import SaleCreate, SaleStatus
from app.schemas.stock import MovementType


class SaleService:
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

            total_profit = Decimal("0")
            for item in payload.items:
                product = products_by_id[item.product_id]
                line_profit = (item.unit_price - product.cost_price) * item.quantity
                total_profit += line_profit

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
                total_profit=total_profit,
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
                line_profit = (item.unit_price - product.cost_price) * item.quantity

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
                    quantity_change=-item.quantity,
                    balance_after=new_quantity,
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
                    select(StockBalance).where(
                        StockBalance.business_id == business_id,
                        StockBalance.product_id == item.product_id,
                    )
                ).scalar_one_or_none()

                if stock_balance:
                    new_quantity = stock_balance.quantity + item.quantity
                    stock_balance.quantity = new_quantity
                    db.add(stock_balance)

                    movement = StockMovement(
                        business_id=business_id,
                        product_id=item.product_id,
                        movement_type=MovementType.RETURN.value,
                        quantity_change=item.quantity,
                        balance_after=new_quantity,
                        reference_type="sale_void",
                        reference_id=sale.id,
                        notes=f"Voided: {reason}",
                        created_by=user_id,
                    )
                    db.add(movement)

            sale.status = SaleStatus.VOIDED.value
            sale.voided_at = datetime.now(timezone.utc)
            sale.void_reason = reason
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

        items = [
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "product_name": product.name,
                "sku": product.sku,
                "quantity": float(item.quantity),
                "unit_price": float(item.unit_price),
                "unit_cost": float(item.unit_cost),
                "line_total": float(item.line_total),
                "line_profit": float((item.unit_price - item.unit_cost) * item.quantity),
            }
            for item, product in rows
        ]

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
            "total_profit": float(sale.total_profit),
            "notes": sale.notes,
            "created_by": str(sale.created_by) if sale.created_by else None,
            "created_at": sale.created_at,
            "voided_at": sale.voided_at,
            "void_reason": sale.void_reason,
        }