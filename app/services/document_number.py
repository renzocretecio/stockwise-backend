import re
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, select

from app.models.document_sequence import BusinessDocumentSequence
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.models.storefront import StoreOrder


class DocumentNumberService:
    """Generate per-business document numbers inside the active transaction."""

    _DOCUMENTS = {
        "purchase": ("PO", Purchase),
        "sale": ("SALE", Sale),
        "store_order": ("ORD", StoreOrder),
    }

    @classmethod
    def next_reference_number(
        cls,
        business_id: str | UUID,
        document_type: str,
        db: Session,
    ) -> str:
        prefix, model = cls._DOCUMENTS[document_type]
        query_business_id = cls._coerce_business_id(business_id)

        # Serializes number generation per business and document type on
        # PostgreSQL, including the first number before a sequence row exists.
        if db.get_bind().dialect.name == "postgresql":
            db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"document-number:{business_id}:{document_type}"},
            )

        sequence = db.execute(
            select(BusinessDocumentSequence)
            .where(
                BusinessDocumentSequence.business_id == query_business_id,
                BusinessDocumentSequence.document_type == document_type,
            )
            .with_for_update()
        ).scalar_one_or_none()

        if sequence is None:
            number = cls._first_available_number(
                business_id=query_business_id,
                prefix=prefix,
                model=model,
                db=db,
            )
            sequence = BusinessDocumentSequence(
                business_id=query_business_id,
                document_type=document_type,
                next_number=number + 1,
            )
            db.add(sequence)
        else:
            number = sequence.next_number
            sequence.next_number += 1

        db.flush()
        return f"{prefix}-{number:06d}"

    @staticmethod
    def _coerce_business_id(business_id: str | UUID) -> str | UUID:
        if isinstance(business_id, UUID):
            return business_id
        try:
            return UUID(str(business_id))
        except ValueError:
            return business_id

    @staticmethod
    def _first_available_number(
        business_id: str | UUID,
        prefix: str,
        model: type[Purchase] | type[Sale] | type[StoreOrder],
        db: Session,
    ) -> int:
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        highest = 0
        values = db.execute(
            select(model.reference_number).where(model.business_id == business_id)
        ).scalars()

        for value in values:
            match = pattern.match(value or "")
            if match:
                highest = max(highest, int(match.group(1)))

        return highest + 1
