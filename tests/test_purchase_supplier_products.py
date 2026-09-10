from decimal import Decimal
from types import SimpleNamespace

from app.services.purchase import PurchaseService


class Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class Database:
    def __init__(self, rows):
        self.rows = rows
        self.added = []

    def execute(self, _statement):
        return Result(self.rows)

    def add(self, item):
        self.added.append(item)


def test_purchase_refreshes_existing_supplier_product_cost():
    product = SimpleNamespace(
        name="Coffee Beans",
        supplier_id="supplier-1",
        lead_time_days=5,
    )
    products = {
        "product-1": product,
    }
    link = SimpleNamespace(
        product_id="product-1",
        unit_cost=Decimal("100.00"),
        is_active=False,
        is_preferred=True,
    )
    database = Database([link])

    PurchaseService._record_supplier_products(
        business_id="business-1",
        supplier_id="supplier-1",
        product_ids=["product-1"],
        products_by_id=products,
        unit_costs={"product-1": Decimal("120.00")},
        db=database,
    )

    assert link.unit_cost == Decimal("120.00")
    assert link.is_active is True
    assert database.added == []


def test_purchase_learns_a_new_supplier_product_relationship():
    product = SimpleNamespace(
        name="Paper Cups",
        supplier_id=None,
        lead_time_days=3,
    )
    products = {
        "product-2": product,
    }
    database = Database([])

    PurchaseService._record_supplier_products(
        business_id="business-1",
        supplier_id="supplier-1",
        product_ids=["product-2"],
        products_by_id=products,
        unit_costs={"product-2": Decimal("80.00")},
        db=database,
    )

    assert len(database.added) == 1
    assert database.added[0].unit_cost == Decimal("80.00")
    assert database.added[0].is_preferred is True
    assert product.supplier_id == "supplier-1"
