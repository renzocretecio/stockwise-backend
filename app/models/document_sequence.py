from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, String
from sqlalchemy.types import UUID as UUID_Type

from app.models.base import Base


class BusinessDocumentSequence(Base):
    """Stores the next human-readable document number for a business."""

    __tablename__ = "business_document_sequences"
    __table_args__ = (
        CheckConstraint("next_number >= 1", name="ck_document_sequence_positive"),
    )

    business_id = Column(
        UUID_Type(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_type = Column(String(30), primary_key=True)
    next_number = Column(Integer, default=1, nullable=False)
