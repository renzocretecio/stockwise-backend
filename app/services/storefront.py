import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.config.settings import settings
from app.models.business import Business
from app.models.category import Category
from app.models.inventory import StockBalance, StockMovement
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.storefront import (
    PublicStore,
    StoreOrder,
    StoreOrderItem,
    StoreProduct,
)
from app.schemas.storefront import (
    DeliveryMethod,
    OutOfStockBehavior,
    PublicOrderCreate,
    StoreOrderStatus,
    StoreOrderStatusUpdate,
    StoreProductBulkPublish,
    StoreProductUpdate,
    StorefrontCreate,
    StorefrontUpdate,
)
from app.services.document_number import DocumentNumberService


class StorefrontService:
    _PAYMENT_METHODS_REQUIRING_INSTRUCTIONS = {
        "gcash",
        "bank_transfer",
    }
    _TRANSITIONS = {
        "new": {"confirmed", "cancelled"},
        "confirmed": {
            "processing",
            "ready",
            "shipped",
            "completed",
            "cancelled",
        },
        "processing": {"ready", "shipped", "completed", "cancelled"},
        "ready": {"shipped", "completed", "cancelled"},
        "shipped": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }

    @classmethod
    def create_store(
        cls,
        business_id: str,
        payload: StorefrontCreate,
        db: Session,
    ) -> dict:
        existing = cls._store_for_business(business_id, db)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This business already has a public store",
            )

        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one_or_none()
        if not business:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found",
            )

        payment_methods = [item.value for item in payload.payment_methods]
        cls._validate_payment_configuration(
            payment_methods,
            payload.payment_instructions,
        )
        if payload.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Publish at least one product before opening the store",
            )

        slug = payload.slug or cls._slugify(payload.name or business.name)
        slug = cls._unique_slug(slug, db)
        store = PublicStore(
            business_id=business_id,
            slug=slug,
            name=payload.name,
            description=payload.description,
            logo_url=payload.logo_url,
            banner_url=payload.banner_url,
            is_active=payload.is_active,
            out_of_stock_behavior=payload.out_of_stock_behavior.value,
            pickup_enabled=payload.pickup_enabled,
            delivery_enabled=payload.delivery_enabled,
            payment_methods=payment_methods,
            payment_instructions=payload.payment_instructions,
        )
        db.add(store)
        try:
            db.commit()
            db.refresh(store)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Store slug is already in use",
            )
        return cls._format_store(store, business.currency_code)

    @classmethod
    def get_store(cls, business_id: str, db: Session) -> dict:
        store = cls._require_store(business_id, db)
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one()
        return cls._format_store(store, business.currency_code)

    @classmethod
    def update_store(
        cls,
        business_id: str,
        payload: StorefrontUpdate,
        db: Session,
    ) -> dict:
        store = cls._require_store(business_id, db)
        changes = payload.model_dump(exclude_unset=True)
        required_fields = {
            "name",
            "out_of_stock_behavior",
            "pickup_enabled",
            "delivery_enabled",
            "payment_methods",
        }
        if any(
            field in changes and changes[field] is None for field in required_fields
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Required store settings cannot be null",
            )
        if "out_of_stock_behavior" in changes:
            changes["out_of_stock_behavior"] = changes["out_of_stock_behavior"].value
        if "payment_methods" in changes:
            changes["payment_methods"] = [
                item.value for item in changes["payment_methods"]
            ]

        pickup = changes.get("pickup_enabled", store.pickup_enabled)
        delivery = changes.get("delivery_enabled", store.delivery_enabled)
        if not pickup and not delivery:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Enable pickup, delivery, or both",
            )

        payment_methods = changes.get(
            "payment_methods",
            store.payment_methods,
        )
        payment_instructions = changes.get(
            "payment_instructions",
            store.payment_instructions,
        )
        cls._validate_payment_configuration(
            payment_methods,
            payment_instructions,
        )

        if changes.get("is_active", store.is_active):
            published_count = db.execute(
                select(func.count(StoreProduct.id)).where(
                    StoreProduct.store_id == store.id,
                    StoreProduct.is_public.is_(True),
                )
            ).scalar_one()
            if published_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Publish at least one product before opening the store"
                    ),
                )

        for field, value in changes.items():
            setattr(store, field, value)
        db.add(store)
        db.commit()
        db.refresh(store)
        business = db.execute(
            select(Business).where(Business.id == business_id)
        ).scalar_one()
        return cls._format_store(store, business.currency_code)

    @classmethod
    def _validate_payment_configuration(
        cls,
        payment_methods: list[str],
        payment_instructions: dict[str, str] | None,
    ) -> None:
        instructions = payment_instructions or {}
        missing = [
            method
            for method in payment_methods
            if method in cls._PAYMENT_METHODS_REQUIRING_INSTRUCTIONS
            and not instructions.get(method, "").strip()
        ]
        if missing:
            labels = {
                "gcash": "GCash",
                "bank_transfer": "bank transfer",
            }
            names = ", ".join(labels[method] for method in missing)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Add payment instructions for {names}",
            )

    @classmethod
    def list_catalog_products(
        cls,
        business_id: str,
        db: Session,
        page: int,
        page_size: int,
        search: str | None,
    ) -> dict:
        store = cls._require_store(business_id, db)
        query = (
            select(Product, StoreProduct, StockBalance, Category)
            .outerjoin(
                StoreProduct,
                (StoreProduct.product_id == Product.id)
                & (StoreProduct.store_id == store.id),
            )
            .outerjoin(
                StockBalance,
                StockBalance.product_id == Product.id,
            )
            .outerjoin(Category, Category.id == Product.category_id)
            .where(
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        )
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.sku.ilike(pattern),
                    StoreProduct.public_name.ilike(pattern),
                )
            )
        total = db.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar_one()
        rows = db.execute(
            query.order_by(Product.name).offset((page - 1) * page_size).limit(page_size)
        ).all()
        products = [cls._format_catalog_product(*row, public=False) for row in rows]
        published_count = db.execute(
            select(func.count(StoreProduct.id))
            .join(Product, Product.id == StoreProduct.product_id)
            .where(
                StoreProduct.store_id == store.id,
                StoreProduct.is_public.is_(True),
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).scalar_one()
        result = cls._paginated("products", products, total, page, page_size)
        result["published_count"] = published_count
        return result

    @classmethod
    def update_catalog_product(
        cls,
        business_id: str,
        product_id: str,
        payload: StoreProductUpdate,
        db: Session,
    ) -> dict:
        store = cls._require_store(business_id, db)
        product = db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        listing = db.execute(
            select(StoreProduct).where(
                StoreProduct.store_id == store.id,
                StoreProduct.product_id == product.id,
            )
        ).scalar_one_or_none()
        values = payload.model_dump(exclude_unset=True)
        if listing is None:
            public_price = values.pop("public_price", None)
            listing = StoreProduct(
                store_id=store.id,
                product_id=product.id,
                public_price=(
                    public_price if public_price is not None else product.selling_price
                ),
                **values,
            )
        else:
            for field, value in values.items():
                if field == "public_price" and value is None:
                    continue
                setattr(listing, field, value)
        db.add(listing)
        db.commit()
        db.refresh(listing)

        stock = db.execute(
            select(StockBalance).where(StockBalance.product_id == product.id)
        ).scalar_one_or_none()
        category = (
            db.execute(
                select(Category).where(Category.id == product.category_id)
            ).scalar_one_or_none()
            if product.category_id
            else None
        )
        return cls._format_catalog_product(
            product,
            listing,
            stock,
            category,
            public=False,
        )

    @classmethod
    def bulk_publish_catalog_products(
        cls,
        business_id: str,
        payload: StoreProductBulkPublish,
        db: Session,
    ) -> dict:
        store = cls._require_store(business_id, db)
        products = db.execute(
            select(Product).where(
                Product.id.in_(payload.product_ids),
                Product.business_id == business_id,
                Product.is_active.is_(True),
            )
        ).scalars().all()
        if len(products) != len(payload.product_ids):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more products were not found",
            )

        listings = db.execute(
            select(StoreProduct).where(
                StoreProduct.store_id == store.id,
                StoreProduct.product_id.in_(payload.product_ids),
            )
        ).scalars().all()
        listings_by_product = {
            listing.product_id: listing for listing in listings
        }

        for product in products:
            listing = listings_by_product.get(product.id)
            if listing is None:
                listing = StoreProduct(
                    store_id=store.id,
                    product_id=product.id,
                    public_price=product.selling_price,
                    is_public=payload.is_public,
                )
            else:
                listing.is_public = payload.is_public
            db.add(listing)

        db.commit()
        return {
            "updated_count": len(products),
            "is_public": payload.is_public,
        }

    @classmethod
    def get_public_store(cls, slug: str, db: Session) -> dict:
        store, business = cls._require_public_store(slug, db)
        return cls._format_store(store, business.currency_code, public=True)

    @classmethod
    def list_public_products(
        cls,
        slug: str,
        db: Session,
        page: int,
        page_size: int,
        search: str | None,
        category_id: str | None,
    ) -> dict:
        store, _business = cls._require_public_store(slug, db)
        query = (
            select(Product, StoreProduct, StockBalance, Category)
            .join(StoreProduct, StoreProduct.product_id == Product.id)
            .outerjoin(
                StockBalance,
                StockBalance.product_id == Product.id,
            )
            .outerjoin(Category, Category.id == Product.category_id)
            .where(
                StoreProduct.store_id == store.id,
                StoreProduct.is_public.is_(True),
                Product.is_active.is_(True),
            )
        )
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    StoreProduct.public_name.ilike(pattern),
                    Product.name.ilike(pattern),
                    StoreProduct.public_description.ilike(pattern),
                )
            )
        if category_id:
            query = query.where(Product.category_id == category_id)
        if store.out_of_stock_behavior == OutOfStockBehavior.HIDE.value:
            query = query.where(
                func.coalesce(StockBalance.quantity, 0)
                - func.coalesce(StockBalance.reserved_quantity, 0)
                > 0
            )

        total = db.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar_one()
        rows = db.execute(
            query.order_by(StoreProduct.sort_order, Product.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        products = [cls._format_catalog_product(*row, public=True) for row in rows]
        return cls._paginated("products", products, total, page, page_size)

    @classmethod
    def list_public_categories(
        cls,
        slug: str,
        db: Session,
    ) -> dict:
        store, _business = cls._require_public_store(slug, db)
        query = (
            select(
                Category.id,
                Category.name,
                func.count(StoreProduct.id).label("product_count"),
            )
            .join(Product, Product.category_id == Category.id)
            .join(StoreProduct, StoreProduct.product_id == Product.id)
            .outerjoin(
                StockBalance,
                StockBalance.product_id == Product.id,
            )
            .where(
                StoreProduct.store_id == store.id,
                StoreProduct.is_public.is_(True),
                Product.is_active.is_(True),
                Category.is_active.is_(True),
            )
        )
        if store.out_of_stock_behavior == OutOfStockBehavior.HIDE.value:
            query = query.where(
                func.coalesce(StockBalance.quantity, 0)
                - func.coalesce(StockBalance.reserved_quantity, 0)
                > 0
            )
        rows = db.execute(
            query.group_by(Category.id, Category.name).order_by(Category.name)
        ).all()
        return {
            "categories": [
                {
                    "id": str(category_id),
                    "name": name,
                    "product_count": product_count,
                }
                for category_id, name, product_count in rows
            ]
        }

    @classmethod
    def create_public_order(
        cls,
        slug: str,
        payload: PublicOrderCreate,
        db: Session,
    ) -> dict:
        store, _business = cls._require_public_store(slug, db)
        cls._validate_order_options(store, payload)
        listing_ids = [item.store_product_id for item in payload.items]
        rows = db.execute(
            select(StoreProduct, Product, StockBalance)
            .join(Product, Product.id == StoreProduct.product_id)
            .outerjoin(
                StockBalance,
                StockBalance.product_id == Product.id,
            )
            .where(
                StoreProduct.id.in_(listing_ids),
                StoreProduct.store_id == store.id,
                StoreProduct.is_public.is_(True),
                Product.is_active.is_(True),
            )
        ).all()
        by_id = {str(listing.id): row for row in rows for listing in [row[0]]}
        missing = {str(item.store_product_id) for item in payload.items} - set(by_id)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="One or more products are unavailable",
            )

        subtotal = Decimal("0")
        lines = []
        for requested in payload.items:
            listing, product, stock = by_id[str(requested.store_product_id)]
            available = cls._available(stock)
            if (
                available < requested.quantity
                and store.out_of_stock_behavior
                != OutOfStockBehavior.CONTINUE_SELLING.value
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"{listing.public_name or product.name} is sold out",
                )
            line_total = Decimal(listing.public_price) * requested.quantity
            subtotal += line_total
            lines.append((listing, product, requested.quantity, line_total))

        order = StoreOrder(
            store_id=store.id,
            business_id=store.business_id,
            reference_number=DocumentNumberService.next_reference_number(
                business_id=str(store.business_id),
                document_type="store_order",
                db=db,
            ),
            status=StoreOrderStatus.NEW.value,
            customer_name=payload.customer_name,
            customer_contact=payload.customer_contact,
            delivery_method=payload.delivery_method.value,
            delivery_address=payload.delivery_address,
            customer_notes=payload.customer_notes,
            payment_method=payload.payment_method.value,
            subtotal=subtotal,
            total_amount=subtotal,
        )
        db.add(order)
        db.flush()
        for listing, product, quantity, line_total in lines:
            db.add(
                StoreOrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=listing.public_name or product.name,
                    sku=product.sku,
                    quantity=quantity,
                    reserved_quantity=Decimal("0"),
                    unit_price=listing.public_price,
                    unit_cost=product.cost_price,
                    line_total=line_total,
                )
            )
        db.commit()
        db.refresh(order)
        return {
            "order": cls._format_order(order, db, public=True),
            "tracking_token": order.tracking_token,
        }

    @classmethod
    def get_public_order(
        cls,
        reference_number: str,
        tracking_token: str,
        db: Session,
    ) -> dict:
        order = db.execute(
            select(StoreOrder).where(
                StoreOrder.reference_number == reference_number,
                StoreOrder.tracking_token == tracking_token,
            )
        ).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return cls._format_order(order, db, public=True)

    @classmethod
    def list_orders(
        cls,
        business_id: str,
        db: Session,
        page: int,
        page_size: int,
        status_filter: str | None,
        search: str | None,
    ) -> dict:
        query = select(StoreOrder).where(StoreOrder.business_id == business_id)
        if status_filter:
            query = query.where(StoreOrder.status == status_filter)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    StoreOrder.reference_number.ilike(pattern),
                    StoreOrder.customer_name.ilike(pattern),
                    StoreOrder.customer_contact.ilike(pattern),
                )
            )
        total = db.execute(
            select(func.count()).select_from(query.subquery())
        ).scalar_one()
        orders = (
            db.execute(
                query.order_by(StoreOrder.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        items = [cls._format_order(order, db) for order in orders]
        return cls._paginated("orders", items, total, page, page_size)

    @classmethod
    def get_order(
        cls,
        business_id: str,
        order_id: str,
        db: Session,
    ) -> dict:
        order = cls._require_order(business_id, order_id, db)
        return cls._format_order(order, db)

    @classmethod
    def update_order_status(
        cls,
        business_id: str,
        order_id: str,
        payload: StoreOrderStatusUpdate,
        user_id: str,
        db: Session,
    ) -> dict:
        try:
            order = cls._require_order(
                business_id,
                order_id,
                db,
                lock=True,
            )
            target = payload.status.value
            if target == order.status:
                return cls._format_order(order, db)
            if target not in cls._TRANSITIONS[order.status]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Order cannot move from '{order.status}' " f"to '{target}'"
                    ),
                )
            if target == StoreOrderStatus.CONFIRMED.value:
                cls._reserve_order(order, user_id, db)
            elif target == StoreOrderStatus.CANCELLED.value:
                cls._cancel_order(
                    order,
                    payload.cancellation_reason or "Cancelled",
                    user_id,
                    db,
                )
            elif target == StoreOrderStatus.COMPLETED.value:
                cls._complete_order(order, user_id, db)
            else:
                cls._advance_order(order, target)
            db.add(order)
            db.commit()
            db.refresh(order)
            return cls._format_order(order, db)
        except HTTPException:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order update conflicted with another request",
            )
        except Exception:
            db.rollback()
            raise

    @classmethod
    def _reserve_order(
        cls,
        order: StoreOrder,
        user_id: str,
        db: Session,
    ) -> None:
        items = cls._order_items(order.id, db)
        balances = cls._locked_balances(order.business_id, items, db)
        insufficient = []
        for item in items:
            balance = balances.get(str(item.product_id))
            available = cls._available(balance)
            if available < item.quantity:
                insufficient.append(
                    f"{item.product_name}: requested {item.quantity}, "
                    f"available {available}"
                )
        if insufficient:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Insufficient stock: " + "; ".join(insufficient),
            )

        for item in items:
            balance = balances[str(item.product_id)]
            balance.reserved_quantity += item.quantity
            item.reserved_quantity = item.quantity
            db.add(balance)
            db.add(item)
        order.status = StoreOrderStatus.CONFIRMED.value
        order.confirmed_by = user_id
        order.confirmed_at = datetime.now(timezone.utc)

    @classmethod
    def _complete_order(
        cls,
        order: StoreOrder,
        user_id: str,
        db: Session,
    ) -> None:
        items = cls._order_items(order.id, db)
        if not items or any(item.reserved_quantity <= 0 for item in items):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Confirm the order before completing it",
            )
        balances = cls._locked_balances(order.business_id, items, db)
        for item in items:
            balance = balances.get(str(item.product_id))
            if (
                balance is None
                or balance.quantity < item.quantity
                or balance.reserved_quantity < item.reserved_quantity
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Reserved stock is unavailable for {item.product_name}",
                )

        sale = Sale(
            business_id=order.business_id,
            reference_number=DocumentNumberService.next_reference_number(
                business_id=str(order.business_id),
                document_type="sale",
                db=db,
            ),
            status="completed",
            subtotal=order.subtotal,
            tax_amount=Decimal("0"),
            discount_amount=Decimal("0"),
            total_amount=order.total_amount,
            payment_method=cls._sale_payment_method(order.payment_method),
            notes=f"Created from online order {order.reference_number}",
            created_by=user_id,
        )
        db.add(sale)
        db.flush()
        for item in items:
            balance = balances[str(item.product_id)]
            balance.quantity -= item.quantity
            balance.reserved_quantity -= item.reserved_quantity
            item.reserved_quantity = Decimal("0")
            db.add(balance)
            db.add(item)
            db.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    unit_cost=item.unit_cost,
                    discount_amount=Decimal("0"),
                    line_total=item.line_total,
                )
            )
            db.add(
                StockMovement(
                    business_id=order.business_id,
                    product_id=item.product_id,
                    movement_type="sale",
                    quantity=-item.quantity,
                    unit_cost=item.unit_cost,
                    reference_type="sale",
                    reference_id=sale.id,
                    notes=f"Sold via online order {order.reference_number}",
                    created_by=user_id,
                )
            )
        order.sale_id = sale.id
        order.status = StoreOrderStatus.COMPLETED.value
        order.completed_by = user_id
        order.completed_at = datetime.now(timezone.utc)

    @classmethod
    def _cancel_order(
        cls,
        order: StoreOrder,
        reason: str,
        user_id: str,
        db: Session,
    ) -> None:
        items = cls._order_items(order.id, db)
        reserved_items = [item for item in items if item.reserved_quantity > 0]
        if reserved_items:
            balances = cls._locked_balances(
                order.business_id,
                reserved_items,
                db,
            )
            for item in reserved_items:
                balance = balances.get(str(item.product_id))
                if balance is None or (
                    balance.reserved_quantity < item.reserved_quantity
                ):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=(
                            "Reserved stock is inconsistent; "
                            "review inventory before cancelling"
                        ),
                    )
                balance.reserved_quantity -= item.reserved_quantity
                item.reserved_quantity = Decimal("0")
                db.add(balance)
                db.add(item)
        order.status = StoreOrderStatus.CANCELLED.value
        order.cancelled_by = user_id
        order.cancelled_at = datetime.now(timezone.utc)
        order.cancellation_reason = reason.strip()

    @staticmethod
    def _advance_order(order: StoreOrder, target: str) -> None:
        now = datetime.now(timezone.utc)
        if target == StoreOrderStatus.PROCESSING.value:
            order.processing_at = now
        elif target == StoreOrderStatus.READY.value:
            order.ready_at = now
        elif target == StoreOrderStatus.SHIPPED.value:
            if order.delivery_method != DeliveryMethod.DELIVERY.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Pickup orders cannot be marked as shipped",
                )
            order.shipped_at = now
        order.status = target

    @staticmethod
    def _order_items(order_id, db: Session) -> list[StoreOrderItem]:
        return (
            db.execute(
                select(StoreOrderItem)
                .where(StoreOrderItem.order_id == order_id)
                .order_by(StoreOrderItem.product_id)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _locked_balances(
        business_id,
        items: list[StoreOrderItem],
        db: Session,
    ) -> dict[str, StockBalance]:
        product_ids = sorted(
            {item.product_id for item in items},
            key=str,
        )
        balances = (
            db.execute(
                select(StockBalance)
                .where(
                    StockBalance.business_id == business_id,
                    StockBalance.product_id.in_(product_ids),
                )
                .order_by(StockBalance.product_id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        return {str(balance.product_id): balance for balance in balances}

    @staticmethod
    def _validate_order_options(
        store: PublicStore,
        payload: PublicOrderCreate,
    ) -> None:
        if (
            payload.delivery_method == DeliveryMethod.PICKUP
            and not store.pickup_enabled
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pickup is not available for this store",
            )
        if (
            payload.delivery_method == DeliveryMethod.DELIVERY
            and not store.delivery_enabled
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Delivery is not available for this store",
            )
        if payload.payment_method.value not in store.payment_methods:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected payment method is not available",
            )

    @staticmethod
    def _sale_payment_method(payment_method: str) -> str:
        return {
            "cod": "cash",
            "pay_on_pickup": "cash",
            "gcash": "e_wallet",
            "bank_transfer": "bank_transfer",
        }.get(payment_method, "other")

    @staticmethod
    def _available(stock: StockBalance | None) -> Decimal:
        if stock is None:
            return Decimal("0")
        return Decimal(stock.quantity) - Decimal(stock.reserved_quantity)

    @classmethod
    def _format_catalog_product(
        cls,
        product: Product,
        listing: StoreProduct | None,
        stock: StockBalance | None,
        category: Category | None,
        public: bool,
    ) -> dict:
        available = cls._available(stock)
        result = {
            "id": str(listing.id) if listing else None,
            "product_id": str(product.id),
            "name": (
                listing.public_name if listing and listing.public_name else product.name
            ),
            "description": (
                listing.public_description
                if listing and listing.public_description is not None
                else product.description
            ),
            "price": float(listing.public_price if listing else product.selling_price),
            "image_url": listing.public_image_url if listing else None,
            "category": (
                {"id": str(category.id), "name": category.name} if category else None
            ),
            "availability": "in_stock" if available > 0 else "sold_out",
        }
        if not public:
            result.update(
                {
                    "sku": product.sku,
                    "is_public": listing.is_public if listing else False,
                    "sort_order": listing.sort_order if listing else 0,
                    "available_quantity": float(available),
                }
            )
        return result

    @staticmethod
    def _format_store(
        store: PublicStore,
        currency_code: str,
        public: bool = False,
    ) -> dict:
        result = {
            "id": str(store.id),
            "slug": store.slug,
            "public_url": (f"{settings.APP_URL.rstrip('/')}/s/{store.slug}"),
            "name": store.name,
            "description": store.description,
            "logo_url": store.logo_url,
            "banner_url": store.banner_url,
            "currency_code": currency_code,
            "pickup_enabled": store.pickup_enabled,
            "delivery_enabled": store.delivery_enabled,
            "payment_methods": store.payment_methods or [],
            "payment_instructions": store.payment_instructions or {},
        }
        if not public:
            result.update(
                {
                    "business_id": str(store.business_id),
                    "is_active": store.is_active,
                    "out_of_stock_behavior": store.out_of_stock_behavior,
                    "created_at": store.created_at,
                    "updated_at": store.updated_at,
                }
            )
        return result

    @classmethod
    def _format_order(
        cls,
        order: StoreOrder,
        db: Session,
        public: bool = False,
    ) -> dict:
        items = cls._order_items(order.id, db)
        store_context = db.execute(
            select(PublicStore, Business)
            .join(Business, Business.id == PublicStore.business_id)
            .where(PublicStore.id == order.store_id)
        ).one()
        store, business = store_context
        payment_instructions = store.payment_instructions or {}
        result = {
            "id": str(order.id),
            "reference_number": order.reference_number,
            "store_name": store.name,
            "store_slug": store.slug,
            "currency_code": business.currency_code,
            "status": order.status,
            "customer_name": order.customer_name,
            "customer_contact": order.customer_contact,
            "delivery_method": order.delivery_method,
            "delivery_address": order.delivery_address,
            "customer_notes": order.customer_notes,
            "payment_method": order.payment_method,
            "subtotal": float(order.subtotal),
            "total_amount": float(order.total_amount),
            "items": [
                {
                    "id": str(item.id),
                    "product_id": str(item.product_id),
                    "product_name": item.product_name,
                    "sku": item.sku,
                    "quantity": float(item.quantity),
                    "unit_price": float(item.unit_price),
                    "line_total": float(item.line_total),
                }
                for item in items
            ],
            "created_at": order.created_at,
            "confirmed_at": order.confirmed_at,
            "processing_at": order.processing_at,
            "ready_at": order.ready_at,
            "shipped_at": order.shipped_at,
            "completed_at": order.completed_at,
            "cancelled_at": order.cancelled_at,
            "cancellation_reason": order.cancellation_reason,
        }
        if public:
            result["payment_instructions"] = payment_instructions.get(
                order.payment_method
            )
        if not public:
            result.update(
                {
                    "store_id": str(order.store_id),
                    "business_id": str(order.business_id),
                    "sale_id": str(order.sale_id) if order.sale_id else None,
                }
            )
        return result

    @staticmethod
    def _paginated(
        key: str,
        items: list[dict],
        total: int,
        page: int,
        page_size: int,
    ) -> dict:
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            key: items,
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
    def _store_for_business(
        business_id: str,
        db: Session,
    ) -> PublicStore | None:
        return db.execute(
            select(PublicStore).where(PublicStore.business_id == business_id)
        ).scalar_one_or_none()

    @classmethod
    def _require_store(
        cls,
        business_id: str,
        db: Session,
    ) -> PublicStore:
        store = cls._store_for_business(business_id, db)
        if not store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Public store has not been created",
            )
        return store

    @staticmethod
    def _require_public_store(
        slug: str,
        db: Session,
    ) -> tuple[PublicStore, Business]:
        row = db.execute(
            select(PublicStore, Business)
            .join(Business, Business.id == PublicStore.business_id)
            .where(
                PublicStore.slug == slug.lower(),
                PublicStore.is_active.is_(True),
                Business.is_active.is_(True),
            )
        ).one_or_none()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Store not found",
            )
        return row

    @staticmethod
    def _require_order(
        business_id: str,
        order_id: str,
        db: Session,
        lock: bool = False,
    ) -> StoreOrder:
        query = select(StoreOrder).where(
            StoreOrder.business_id == business_id,
            StoreOrder.id == order_id,
        )
        if lock:
            query = query.with_for_update()
        order = db.execute(query).scalar_one_or_none()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )
        return order

    @staticmethod
    def _slugify(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
        return slug[:140] or "store"

    @staticmethod
    def _unique_slug(base: str, db: Session) -> str:
        slug = base
        suffix = 2
        while db.execute(
            select(PublicStore.id).where(PublicStore.slug == slug)
        ).scalar_one_or_none():
            slug = f"{base[:140]}-{suffix}"
            suffix += 1
        return slug
