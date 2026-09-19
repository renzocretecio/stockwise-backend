import csv
import io

import pandas as pd
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Supplier
from app.schemas.supplier_import import (
    SupplierImportPreview,
    SupplierImportRow,
    SupplierImportRowError,
)
from app.services.product_import_service import (
    decode_csv_bytes,
    detect_import_format,
    normalize_header,
    normalize_raw_row,
    parse_integer,
)


def _optional(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _validation_message(error: ValidationError) -> str:
    first_error = error.errors()[0]
    location = first_error.get("loc", ())
    field = str(location[-1]).replace("_", " ") if location else "Value"
    message = str(first_error.get("msg", "is invalid"))
    return f"{field.capitalize()}: {message}"


def _parse_supplier_rows(
    raw_rows: list[dict[object, object]],
    source_name: str,
    existing_names: set[str] | None = None,
) -> SupplierImportPreview:
    normalized_rows = []

    for raw_row in raw_rows:
        normalized_row = normalize_raw_row(raw_row)
        if any(normalized_row.values()):
            normalized_rows.append(normalized_row)

    if not normalized_rows:
        return SupplierImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                SupplierImportRowError(
                    row_number=1,
                    message=f"{source_name} has no data rows",
                )
            ],
        )

    if "name" not in normalized_rows[0]:
        return SupplierImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                SupplierImportRowError(
                    row_number=1,
                    message="Missing required column: name",
                )
            ],
        )

    rows: list[SupplierImportRow] = []
    errors: list[SupplierImportRowError] = []
    seen_names: set[str] = set()
    unavailable_names = {name.strip().casefold() for name in (existing_names or set())}

    for row_number, row in enumerate(normalized_rows, start=2):
        try:
            name = row.get("name", "").strip()
            normalized_name = name.casefold()

            if not name:
                raise ValueError("Supplier name is required")

            if normalized_name in seen_names:
                raise ValueError(f"Duplicate supplier name in file: {name}")

            if normalized_name in unavailable_names:
                raise ValueError(f"Supplier already exists: {name}")

            parsed_row = SupplierImportRow(
                row_number=row_number,
                name=name,
                contact_person=_optional(row.get("contact_person")),
                email=_optional(row.get("email")),
                phone=_optional(row.get("phone")),
                address=_optional(row.get("address")),
                payment_terms=_optional(row.get("payment_terms")),
                lead_time_days=parse_integer(
                    row.get("lead_time_days"),
                    default=3,
                ),
                notes=_optional(row.get("notes")),
            )
            seen_names.add(normalized_name)
            rows.append(parsed_row)
        except ValidationError as exc:
            errors.append(
                SupplierImportRowError(
                    row_number=row_number,
                    message=_validation_message(exc),
                )
            )
        except (TypeError, ValueError) as exc:
            errors.append(
                SupplierImportRowError(
                    row_number=row_number,
                    message=str(exc),
                )
            )

    return SupplierImportPreview(
        total_rows=len(normalized_rows),
        valid_rows=len(rows),
        invalid_rows=len(errors),
        rows=rows,
        errors=errors,
    )


def parse_supplier_csv(
    file_bytes: bytes,
    existing_names: set[str] | None = None,
) -> SupplierImportPreview:
    try:
        text = decode_csv_bytes(file_bytes)
        reader = csv.DictReader(
            io.StringIO(text),
            skipinitialspace=True,
        )

        if not reader.fieldnames:
            return SupplierImportPreview(
                total_rows=0,
                valid_rows=0,
                invalid_rows=0,
                rows=[],
                errors=[
                    SupplierImportRowError(
                        row_number=1,
                        message="CSV has no header row",
                    )
                ],
            )

        return _parse_supplier_rows(
            list(reader),
            "CSV",
            existing_names,
        )
    except Exception as exc:
        return SupplierImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                SupplierImportRowError(
                    row_number=1,
                    message=f"Failed to parse CSV: {exc}",
                )
            ],
        )


def parse_supplier_xlsx(
    file_bytes: bytes,
    existing_names: set[str] | None = None,
) -> SupplierImportPreview:
    try:
        dataframe = pd.read_excel(
            io.BytesIO(file_bytes),
            engine="openpyxl",
        )
        dataframe.columns = [normalize_header(column) for column in dataframe.columns]

        return _parse_supplier_rows(
            dataframe.to_dict(orient="records"),
            "XLSX",
            existing_names,
        )
    except Exception as exc:
        return SupplierImportPreview(
            total_rows=0,
            valid_rows=0,
            invalid_rows=0,
            rows=[],
            errors=[
                SupplierImportRowError(
                    row_number=1,
                    message=f"Failed to read XLSX file: {exc}",
                )
            ],
        )


def parse_supplier_import(
    file_bytes: bytes,
    filename: str | None = None,
    content_type: str | None = None,
    existing_names: set[str] | None = None,
) -> SupplierImportPreview:
    detected_format = detect_import_format(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )

    if detected_format == "xlsx":
        return parse_supplier_xlsx(file_bytes, existing_names)

    return parse_supplier_csv(file_bytes, existing_names)


def commit_supplier_import(
    session: Session,
    business_id,
    rows: list[SupplierImportRow],
) -> dict:
    errors: list[dict] = []
    seen_names: set[str] = set()

    try:
        existing_names = {
            name.strip().casefold()
            for name in session.scalars(
                select(Supplier.name).where(
                    Supplier.business_id == business_id,
                    Supplier.is_active.is_(True),
                )
            ).all()
        }

        for row in rows:
            normalized_name = row.name.strip().casefold()

            if normalized_name in seen_names:
                errors.append(
                    {
                        "row_number": row.row_number,
                        "field": "name",
                        "message": (f"Duplicate supplier name in import: {row.name}"),
                    }
                )
                continue

            seen_names.add(normalized_name)

            if normalized_name in existing_names:
                errors.append(
                    {
                        "row_number": row.row_number,
                        "field": "name",
                        "message": f"Supplier already exists: {row.name}",
                    }
                )

        if errors:
            return {
                "created": 0,
                "errors": errors,
                "message": "Import cancelled due to validation errors",
            }

        suppliers = [
            Supplier(
                business_id=business_id,
                name=row.name.strip(),
                contact_person=row.contact_person,
                email=str(row.email) if row.email else None,
                phone=row.phone,
                address=row.address,
                payment_terms=row.payment_terms,
                lead_time_days=row.lead_time_days,
                notes=row.notes,
                is_active=True,
            )
            for row in rows
        ]
        session.add_all(suppliers)
        session.commit()

        return {
            "created": len(suppliers),
            "errors": [],
            "message": f"Successfully imported {len(suppliers)} suppliers",
        }
    except HTTPException:
        session.rollback()
        raise
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
