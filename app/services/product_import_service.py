
import csv
import io
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import StockBalance
from app.models.product import Product
from app.models.product import Supplier
from app.models.category import Category
from app.schemas.product_import import (
    ImportRowError,
    ProductImportPreview,
    ProductImportRow,
)


SUPPORTED_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "cp1252",
    "latin-1",
)


def parse_bool(value: object) -> bool:
    if value is None:
        return False

    normalized = str(value).strip().lower()

    if normalized in {"true", "yes", "1", "y"}:
        return True

    if normalized in {"false", "no", "0", "n", ""}:
        return False

    raise ValueError("Expected true or false")


def parse_decimal(
    value: object,
    default: str = "0",
) -> Decimal:
    if value is None or str(value).strip() == "":
        raw_value = default
    else:
        raw_value = str(value).strip()

    # Remove common spreadsheet formatting.
    raw_value = (
        raw_value
        .replace(",", "")
        .replace("₱", "")
        .replace("$", "")
        .strip()
    )

    try:
        return Decimal(raw_value)
    except InvalidOperation as exc:
        raise ValueError(
            f"Expected a valid number, got: {raw_value}"
        ) from exc


def parse_integer(
    value: object,
    default: int = 3,
) -> int:
    if value is None or str(value).strip() == "":
        return default

    raw_value = str(value).strip()

    try:
        return int(float(raw_value))
    except ValueError as exc:
        raise ValueError(
            f"Expected a whole number, got: {raw_value}"
        ) from exc


def normalize_header(value: object) -> str:
    if value is None:
        return ""

    return (
        str(value)
        .replace("\ufeff", "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def normalize_cell(value: object) -> str:
    if value is None:
        return ""

    if pd.isna(value):
        return ""

    return str(value).strip()


def normalize_raw_row(
    raw_row: dict[object, object],
) -> dict[str, str]:
    return {
        normalize_header(key): normalize_cell(value)
        for key, value in raw_row.items()
        if key is not None
    }


def _parse_product_rows(
    raw_rows: list[dict[object, object]],
    source_name: str,
) -> ProductImportPreview:
    required_columns = {
        "name",
        "unit",
        "cost_price",
        "selling_price",
    }

    if not raw_rows:
        return ProductImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                ImportRowError(
                    row_number=1,
                    message=f"{source_name} has no data rows",
                )
            ],
        )

    normalized_rows = [
        normalize_raw_row(raw_row)
        for raw_row in raw_rows
    ]

    headers = set(normalized_rows[0].keys())
    missing_columns = required_columns - headers

    if missing_columns:
        return ProductImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                ImportRowError(
                    row_number=1,
                    message=(
                        "Missing required columns: "
                        + ", ".join(sorted(missing_columns))
                    ),
                )
            ],
        )

    rows: list[ProductImportRow] = []
    errors: list[ImportRowError] = []

    for row_number, row in enumerate(
        normalized_rows,
        start=2,
    ):
        try:
            name = row.get("name", "").strip()

            if not name:
                raise ValueError(
                    "Product name is required"
                )

            parsed_row = ProductImportRow(
                row_number=row_number,
                sku=row.get("sku") or None,
                barcode=row.get("barcode") or None,
                name=name,
                description=row.get("description") or None,
                category=row.get("category") or None,
                brand=row.get("brand") or None,
                unit=row.get("unit") or "unit",
                cost_price=parse_decimal(
                    row.get("cost_price")
                ),
                selling_price=parse_decimal(
                    row.get("selling_price")
                ),
                reorder_point=parse_decimal(
                    row.get("reorder_point"),
                    default="0",
                ),
                safety_stock=parse_decimal(
                    row.get("safety_stock"),
                    default="0",
                ),
                lead_time_days=parse_integer(
                    row.get("lead_time_days"),
                    default=3,
                ),
                is_perishable=parse_bool(
                    row.get("is_perishable")
                ),
                supplier_name=row.get("supplier_name")
                or None,
            )

            rows.append(parsed_row)

        except (ValueError, TypeError) as exc:
            errors.append(
                ImportRowError(
                    row_number=row_number,
                    message=str(exc),
                )
            )

    return ProductImportPreview(
        total_rows=len(normalized_rows),
        valid_rows=len(rows),
        invalid_rows=len(errors),
        rows=rows,
        errors=errors,
    )


def decode_csv_bytes(file_bytes: bytes) -> str:
    encodings = (
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    )

    for encoding in encodings:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise ValueError(
        "Unsupported file encoding. "
        "Save the CSV as UTF-8 and try again."
    )


def parse_product_csv(
    file_bytes: bytes,
) -> ProductImportPreview:
    try:
        text = decode_csv_bytes(file_bytes)

        reader = csv.DictReader(
            io.StringIO(text),
            skipinitialspace=True,
        )

        if not reader.fieldnames:
            return ProductImportPreview(
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
                rows=[],
                errors=[
                    ImportRowError(
                        row_number=1,
                        message="CSV has no header row",
                    )
                ],
            )

        raw_rows = list(reader)

        return _parse_product_rows(
            raw_rows,
            "CSV",
        )

    except Exception as exc:
        return ProductImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                ImportRowError(
                    row_number=1,
                    message=f"Failed to parse CSV: {exc}",
                )
            ],
        )


def parse_product_xlsx(
    file_bytes: bytes,
) -> ProductImportPreview:
    try:
        dataframe = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl",
        )

        dataframe.columns = [
            normalize_header(column)
            for column in dataframe.columns
        ]

        raw_rows = dataframe.to_dict(
            orient="records"
        )

        return _parse_product_rows(
            raw_rows,
            "XLSX",
        )

    except Exception as exc:
        return ProductImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                ImportRowError(
                    row_number=1,
                    message=f"Failed to read XLSX file: {exc}",
                )
            ],
        )


def detect_import_format(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> str:
    if file_bytes.startswith(b"PK"):
        return "xlsx"

    if filename:
        lower_name = filename.lower()

        if lower_name.endswith(".xlsx"):
            return "xlsx"

        if lower_name.endswith(".csv"):
            return "csv"

    if content_type:
        lower_type = content_type.lower()

        if (
            "spreadsheet" in lower_type
            or "excel" in lower_type
            or "xlsx" in lower_type
        ):
            return "xlsx"

        if "csv" in lower_type:
            return "csv"

    return "csv"


def parse_product_import(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
) -> ProductImportPreview:
    detected_format = detect_import_format(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )

    if detected_format == "xlsx":
        return parse_product_xlsx(file_bytes)

    return parse_product_csv(file_bytes)


def commit_product_import(
    session: Session,
    business_id,
    user_id,
    rows: list[ProductImportRow],
):
    created_products = []
    errors = []

    try:
        for row in rows:
            if row.sku:
                duplicate_sku = session.scalar(
                    select(Product).where(
                        Product.business_id == business_id,
                        Product.sku == row.sku,
                    )
                )

                if duplicate_sku:
                    errors.append({
                        "row_number": row.row_number,
                        "field": "sku",
                        "message": (
                            f"SKU already exists: {row.sku}"
                        ),
                    })
                    continue

            if row.barcode:
                duplicate_barcode = session.scalar(
                    select(Product).where(
                        Product.business_id == business_id,
                        Product.barcode == row.barcode,
                    )
                )

                if duplicate_barcode:
                    errors.append({
                        "row_number": row.row_number,
                        "field": "barcode",
                        "message": (
                            f"Barcode already exists: "
                            f"{row.barcode}"
                        ),
                    })
                    continue

            supplier_id = None

            if row.supplier_name:
                supplier = session.scalar(
                    select(Supplier).where(
                        Supplier.business_id == business_id,
                        Supplier.name.ilike(
                            row.supplier_name.strip()
                        ),
                        Supplier.is_active.is_(True),
                    )
                )

                if supplier is None:
                    errors.append({
                        "row_number": row.row_number,
                        "field": "supplier_name",
                        "message": (
                            f"Supplier not found: "
                            f"{row.supplier_name}"
                        ),
                    })
                    continue

                supplier_id = supplier.id

            category_id = None

            if row.category:
                category = session.scalar(
                    select(Category).where(
                        Category.business_id == business_id,
                        Category.name.ilike(
                            row.category.strip()
                        ),
                        Category.is_active.is_(True),
                    )
                )

                if category is None:
                    errors.append({
                        "row_number": row.row_number,
                        "field": "category",
                        "message": (
                            f"Category not found: {row.category}"
                        ),
                    })
                    continue

                category_id = category.id

            product = Product(
                business_id=business_id,
                supplier_id=supplier_id,
                sku=row.sku,
                barcode=row.barcode,
                name=row.name,
                normalized_name=row.name.lower().strip(),
                description=row.description,
                category_id=category_id,
                brand=row.brand,
                unit=row.unit,
                cost_price=row.cost_price,
                selling_price=row.selling_price,
                reorder_point=row.reorder_point,
                safety_stock=row.safety_stock,
                lead_time_days=row.lead_time_days,
                is_perishable=row.is_perishable,
            )

            session.add(product)
            session.flush()

            stock_balance = StockBalance(
                business_id=business_id,
                product_id=product.id,
                quantity=Decimal("0"),
                reserved_quantity=Decimal("0"),
                average_cost=row.cost_price,
            )

            session.add(stock_balance)
            created_products.append(product)

        if errors:
            session.rollback()

            return {
                "created": 0,
                "errors": errors,
                "message": (
                    "Import cancelled due to "
                    "validation errors"
                ),
            }

        session.commit()

        return {
            "created": len(created_products),
            "errors": [],
            "message": (
                f"Successfully imported "
                f"{len(created_products)} products"
            ),
        }

    except Exception as exc:
        session.rollback()

        return {
            "created": 0,
            "errors": [
                {
                    "row_number": 0,
                    "field": "database",
                    "message": f"Database error: {exc}",
                }
            ],
            "message": "Import failed",
        }