import io

import pandas as pd

from app.services.supplier_import_service import (
    commit_supplier_import,
    parse_supplier_csv,
    parse_supplier_import,
)
from app.schemas.supplier_import import SupplierImportRow


class _ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Session:
    def __init__(self, existing_names=None):
        self.existing_names = existing_names or []
        self.added = []
        self.committed = False
        self.rolled_back = False

    def scalars(self, _statement):
        return _ScalarResult(self.existing_names)

    def add_all(self, records):
        self.added.extend(records)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_parse_supplier_csv_accepts_optional_columns():
    csv_data = (
        b"name,contact_person,email,lead_time_days\n"
        b"North Supply,Ana,ana@example.com,5\n"
    )

    preview = parse_supplier_csv(csv_data)

    assert preview.total_rows == 1
    assert preview.valid_rows == 1
    assert preview.invalid_rows == 0
    assert preview.rows[0].name == "North Supply"
    assert preview.rows[0].lead_time_days == 5


def test_parse_supplier_csv_rejects_duplicate_names():
    csv_data = b"name\nNorth Supply\nnorth supply\n"

    preview = parse_supplier_csv(csv_data)

    assert preview.total_rows == 2
    assert preview.valid_rows == 1
    assert preview.invalid_rows == 1
    assert "Duplicate supplier name" in preview.errors[0].message


def test_parse_supplier_csv_rejects_existing_name():
    csv_data = b"name\nNorth Supply\n"

    preview = parse_supplier_csv(
        csv_data,
        existing_names={"NORTH SUPPLY"},
    )

    assert preview.valid_rows == 0
    assert preview.invalid_rows == 1
    assert "already exists" in preview.errors[0].message


def test_parse_supplier_xlsx_accepts_excel_rows():
    workbook = io.BytesIO()
    dataframe = pd.DataFrame(
        [
            {
                "name": "North Supply",
                "phone": "+63 900 000 0000",
            },
            {
                "name": "South Supply",
                "payment_terms": "Net 30",
            },
        ]
    )

    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False)

    preview = parse_supplier_import(
        workbook.getvalue(),
        filename="suppliers.xlsx",
    )

    assert preview.total_rows == 2
    assert preview.valid_rows == 2
    assert preview.invalid_rows == 0
    assert [row.name for row in preview.rows] == [
        "North Supply",
        "South Supply",
    ]


def test_commit_supplier_import_creates_all_rows_atomically():
    session = _Session()
    rows = [
        SupplierImportRow(
            row_number=2,
            name="North Supply",
            email="north@example.com",
        ),
        SupplierImportRow(
            row_number=3,
            name="South Supply",
        ),
    ]

    result = commit_supplier_import(
        session=session,
        business_id="business-id",
        rows=rows,
    )

    assert result["created"] == 2
    assert result["errors"] == []
    assert len(session.added) == 2
    assert session.committed is True


def test_commit_supplier_import_rejects_existing_supplier():
    session = _Session(existing_names=["NORTH SUPPLY"])
    rows = [
        SupplierImportRow(
            row_number=2,
            name="North Supply",
        )
    ]

    result = commit_supplier_import(
        session=session,
        business_id="business-id",
        rows=rows,
    )

    assert result["created"] == 0
    assert result["errors"][0]["field"] == "name"
    assert session.added == []
    assert session.committed is False
