from types import SimpleNamespace

from app.models.document_sequence import BusinessDocumentSequence
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.services.document_number import DocumentNumberService


class _ScalarResult:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return iter(self.values)


class _DocumentNumberSession:
    def __init__(self, existing_references=None):
        self.sequence = None
        self.existing_references = existing_references or []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

    def execute(self, statement, _parameters=None):
        entity = statement.column_descriptions[0].get("entity")
        if entity is BusinessDocumentSequence:
            return _ScalarResult(value=self.sequence)
        if entity in {Purchase, Sale}:
            return _ScalarResult(values=self.existing_references)
        raise AssertionError("Unexpected statement")

    def add(self, sequence):
        self.sequence = sequence

    def flush(self):
        pass


def test_document_numbers_increment_per_document_sequence():
    purchases = _DocumentNumberSession()

    assert (
        DocumentNumberService.next_reference_number(
            "business-1",
            "purchase",
            purchases,
        )
        == "PO-000001"
    )
    assert (
        DocumentNumberService.next_reference_number(
            "business-1",
            "purchase",
            purchases,
        )
        == "PO-000002"
    )

    sales = _DocumentNumberSession()
    assert (
        DocumentNumberService.next_reference_number(
            "business-1",
            "sale",
            sales,
        )
        == "SALE-000001"
    )


def test_document_numbers_continue_after_existing_generated_numbers():
    db = _DocumentNumberSession(
        existing_references=["PO-000009", "PO-000003"],
    )

    reference = DocumentNumberService.next_reference_number(
        "business-1",
        "purchase",
        db,
    )

    assert reference == "PO-000010"
