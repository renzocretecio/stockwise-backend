import io

from app.services.product_import_service import parse_product_csv


def test_parse_product_csv_accepts_standard_csv():
    csv_data = b"name,unit,cost_price,selling_price\nWidget,pcs,10.00,15.00\n"

    preview = parse_product_csv(csv_data)

    assert preview.total_rows == 1
    assert preview.valid_rows == 1
    assert preview.invalid_rows == 0
    assert preview.rows[0].name == "Widget"
    assert preview.rows[0].cost_price == 10
    assert preview.rows[0].selling_price == 15


def test_parse_product_xlsx_accepts_excel_rows():
    # The Excel path is implemented via pandas and should parse workbook rows into the same model.
    import pandas as pd

    workbook = io.BytesIO()
    df = pd.DataFrame([
        {"name": "Widget", "unit": "pcs", "cost_price": 10.0, "selling_price": 15.0},
        {"name": "Gadget", "unit": "box", "cost_price": 22.5, "selling_price": 33.75},
    ])
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    workbook_bytes = workbook.getvalue()

    from app.services.product_import_service import parse_product_import

    preview = parse_product_import(workbook_bytes, filename="products.xlsx")

    assert preview.total_rows == 2
    assert preview.valid_rows == 2
    assert preview.invalid_rows == 0
    assert [row.name for row in preview.rows] == ["Widget", "Gadget"]
