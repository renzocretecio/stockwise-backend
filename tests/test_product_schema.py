from app.schemas.product import ProductCreate, ProductUpdate


def test_product_create_converts_blank_optional_ids_to_none():
    product = ProductCreate(
        name="Headphones",
        supplier_id="",
        category_id="   ",
        cost_price="800",
        selling_price="1000",
    )

    assert product.supplier_id is None
    assert product.category_id is None


def test_product_update_converts_blank_supplier_id_to_none():
    product = ProductUpdate(supplier_id="")

    assert product.supplier_id is None
