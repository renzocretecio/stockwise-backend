from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.schemas.sync import ReferenceDataResponse
from app.services.reference_data import ReferenceDataService


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class Database:
    def __init__(self, *results):
        self.results = list(results)

    def execute(self, _statement):
        return Result(self.results.pop(0))


def test_reference_catalog_contains_compact_form_data():
    business_id = uuid4()
    product_id = uuid4()
    supplier_id = uuid4()
    category_id = uuid4()
    now = datetime.now(timezone.utc)
    product = SimpleNamespace(
        id=product_id,
        name="Wireless Earbuds",
        sku="EAR-001",
        barcode=None,
        supplier_id=supplier_id,
        category_id=category_id,
        cost_price=Decimal("350.00"),
        selling_price=Decimal("500.00"),
        unit="unit",
        reorder_point=Decimal("10.000"),
        safety_stock=Decimal("5.000"),
        lead_time_days=7,
        is_perishable=False,
        updated_at=now,
    )
    supplier = SimpleNamespace(
        id=supplier_id,
        name="Demo Tech Distribution",
        lead_time_days=7,
        updated_at=now,
    )
    supplier_product = SimpleNamespace(
        product_id=product_id,
        supplier_id=supplier_id,
        supplier_sku="SUP-EAR-01",
        unit_cost=Decimal("340.00"),
        lead_time_days=7,
        minimum_order_quantity=Decimal("5.000"),
        pack_size=Decimal("1.000"),
        is_preferred=True,
        updated_at=now,
    )
    category = SimpleNamespace(
        id=category_id,
        name="Electronics",
        updated_at=now,
    )
    balance = SimpleNamespace(
        product_id=product_id,
        quantity=Decimal("18.000"),
        reserved_quantity=Decimal("2.000"),
        average_cost=Decimal("340.00"),
        updated_at=now,
    )
    database = Database(
        [product],
        [category],
        [supplier],
        [supplier_product],
        [balance],
    )

    result = ReferenceDataService.get_catalog(
        str(business_id),
        database,
        include_suppliers=True,
        include_stock=True,
    )
    response = ReferenceDataResponse.model_validate(result)

    assert response.business_id == business_id
    assert response.products[0].id == product_id
    assert response.products[0].cost_price == Decimal("350.00")
    assert response.suppliers[0].id == supplier_id
    assert response.supplier_products[0].product_id == product_id
    assert response.supplier_products[0].unit_cost == Decimal("340.00")
    assert response.categories[0].id == category_id
    assert response.stock_balances[0].quantity == Decimal("18.000")


def test_reference_catalog_omits_sections_without_permission():
    database = Database([], [])

    result = ReferenceDataService.get_catalog(
        str(uuid4()),
        database,
        include_suppliers=False,
        include_stock=False,
    )

    assert result["suppliers"] == []
    assert result["supplier_products"] == []
    assert result["stock_balances"] == []
    assert database.results == []
