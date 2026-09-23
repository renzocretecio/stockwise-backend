from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import UUID as UUIDType

from app.models import Base
from app.models.auth import User
from app.models.business import Business
from app.models.category import Category
from app.models.document_sequence import BusinessDocumentSequence
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
    PublicOrderCreate,
    StoreOrderStatusUpdate,
    StoreProductBulkPublish,
    StorefrontCreate,
    StorefrontUpdate,
)
from app.services.storefront import StorefrontService


@compiles(UUIDType, "sqlite")
def _compile_uuid_for_sqlite(_type, _compiler, **_kwargs):
    return "CHAR(36)"


def _database():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Business.__table__,
            Category.__table__,
            User.__table__,
            Product.__table__,
            StockBalance.__table__,
            PublicStore.__table__,
            StoreProduct.__table__,
            Sale.__table__,
            SaleItem.__table__,
            StoreOrder.__table__,
            StoreOrderItem.__table__,
            StockMovement.__table__,
            BusinessDocumentSequence.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def _order_fixture(db):
    business = Business(name="Demo Store", slug="demo-store")
    user = User(
        email="owner@example.com",
        password_hash="hash",
        first_name="Owner",
    )
    db.add_all([business, user])
    db.flush()
    product = Product(
        business_id=business.id,
        name="Coffee Beans",
        normalized_name="coffee beans",
        unit="bag",
        cost_price=Decimal("100"),
        selling_price=Decimal("150"),
    )
    store = PublicStore(
        business_id=business.id,
        slug="demo-store-online",
        name="Demo Store",
        is_active=True,
        payment_methods=["cod"],
        payment_instructions={},
    )
    db.add_all([product, store])
    db.flush()
    balance = StockBalance(
        business_id=business.id,
        product_id=product.id,
        quantity=Decimal("5"),
        reserved_quantity=Decimal("0"),
    )
    listing = StoreProduct(
        store_id=store.id,
        product_id=product.id,
        is_public=True,
        public_price=Decimal("150"),
    )
    order = StoreOrder(
        store_id=store.id,
        business_id=business.id,
        reference_number="ORD-000001",
        status="new",
        customer_name="Customer",
        customer_contact="09170000000",
        delivery_method="pickup",
        payment_method="pay_on_pickup",
        subtotal=Decimal("300"),
        total_amount=Decimal("300"),
    )
    db.add_all([balance, listing, order])
    db.flush()
    db.add(
        StoreOrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            quantity=Decimal("2"),
            reserved_quantity=Decimal("0"),
            unit_price=Decimal("150"),
            unit_cost=Decimal("100"),
            line_total=Decimal("300"),
        )
    )
    db.commit()
    return business, user, product, balance, order


def test_confirm_then_complete_reserves_and_sells_once():
    db = _database()
    business, user, product, balance, order = _order_fixture(db)

    StorefrontService.update_order_status(
        business.id,
        order.id,
        StoreOrderStatusUpdate(status="confirmed"),
        user.id,
        db,
    )
    db.refresh(balance)
    assert balance.quantity == Decimal("5.000")
    assert balance.reserved_quantity == Decimal("2.000")
    assert db.execute(select(Sale)).scalars().all() == []

    result = StorefrontService.update_order_status(
        business.id,
        order.id,
        StoreOrderStatusUpdate(status="completed"),
        user.id,
        db,
    )

    db.refresh(balance)
    assert result["status"] == "completed"
    assert result["sale_id"] is not None
    assert balance.quantity == Decimal("3.000")
    assert balance.reserved_quantity == Decimal("0.000")
    movements = db.execute(select(StockMovement)).scalars().all()
    assert len(movements) == 1
    assert movements[0].quantity == Decimal("-2.000")
    assert len(db.execute(select(Sale)).scalars().all()) == 1


def test_cancelling_confirmed_order_releases_stock():
    db = _database()
    business, user, _product, balance, order = _order_fixture(db)
    StorefrontService.update_order_status(
        business.id,
        order.id,
        StoreOrderStatusUpdate(status="confirmed"),
        user.id,
        db,
    )

    result = StorefrontService.update_order_status(
        business.id,
        order.id,
        StoreOrderStatusUpdate(
            status="cancelled",
            cancellation_reason="Customer changed their mind",
        ),
        user.id,
        db,
    )

    db.refresh(balance)
    assert result["status"] == "cancelled"
    assert balance.quantity == Decimal("5.000")
    assert balance.reserved_quantity == Decimal("0.000")
    assert db.execute(select(Sale)).scalars().all() == []


def test_public_order_schema_requires_delivery_address():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PublicOrderCreate(
            items=[{"store_product_id": "item-1", "quantity": "1"}],
            customer_name="Customer",
            customer_contact="09170000000",
            delivery_method="delivery",
            payment_method="cod",
        )


def test_public_submission_snapshots_price_without_reserving_stock():
    db = _database()
    _business, _user, _product, balance, _order = _order_fixture(db)
    listing = db.execute(select(StoreProduct)).scalar_one()

    result = StorefrontService.create_public_order(
        "demo-store-online",
        PublicOrderCreate(
            items=[
                {
                    "store_product_id": listing.id,
                    "quantity": "1",
                }
            ],
            customer_name="Online Customer",
            customer_contact="09171234567",
            delivery_method="pickup",
            payment_method="cod",
        ),
        db,
    )

    db.refresh(balance)
    assert result["order"]["status"] == "new"
    assert result["order"]["total_amount"] == 150.0
    assert len(result["tracking_token"]) >= 20
    assert balance.quantity == Decimal("5.000")
    assert balance.reserved_quantity == Decimal("0.000")


def test_bulk_publish_creates_and_updates_store_listings():
    db = _database()
    business, _user, product, _balance, _order = _order_fixture(db)
    listing = db.execute(select(StoreProduct)).scalar_one()
    listing.is_public = False
    db.add(listing)
    db.commit()

    result = StorefrontService.bulk_publish_catalog_products(
        business.id,
        StoreProductBulkPublish(
            product_ids=[product.id],
            is_public=True,
        ),
        db,
    )

    db.refresh(listing)
    assert result == {"updated_count": 1, "is_public": True}
    assert listing.is_public is True


def test_store_cannot_open_before_a_product_is_published():
    db = _database()
    business = Business(name="Empty Store", slug="empty-store")
    db.add(business)
    db.commit()

    StorefrontService.create_store(
        business.id,
        StorefrontCreate(name="Empty Store"),
        db,
    )

    with pytest.raises(HTTPException) as error:
        StorefrontService.update_store(
            business.id,
            StorefrontUpdate(is_active=True),
            db,
        )

    assert error.value.status_code == 422
    assert error.value.detail == (
        "Publish at least one product before opening the store"
    )


def test_digital_payment_method_requires_instructions():
    db = _database()
    business = Business(name="Digital Store", slug="digital-store")
    db.add(business)
    db.commit()

    with pytest.raises(HTTPException) as error:
        StorefrontService.create_store(
            business.id,
            StorefrontCreate(
                name="Digital Store",
                payment_methods=["gcash"],
            ),
            db,
        )

    assert error.value.status_code == 422
    assert error.value.detail == "Add payment instructions for GCash"


def test_gcash_maps_to_supported_sale_payment_method():
    assert StorefrontService._sale_payment_method("gcash") == "e_wallet"


def test_catalog_published_count_is_not_limited_to_current_page():
    db = _database()
    business, _user, _product, _balance, _order = _order_fixture(db)
    other = Product(
        business_id=business.id,
        name="Tea",
        normalized_name="tea",
        unit="bag",
        cost_price=Decimal("50"),
        selling_price=Decimal("80"),
    )
    db.add(other)
    db.commit()

    result = StorefrontService.list_catalog_products(
        business.id, db, page=1, page_size=1, search="Tea"
    )

    assert result["pagination"]["total"] == 1
    assert result["published_count"] == 1
