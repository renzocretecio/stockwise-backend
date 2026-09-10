"""add business document sequences

Revision ID: l3f4a5b6c7d8
Revises: k2f3a4b5c6d7
Create Date: 2026-09-10
"""

from alembic import op
import sqlalchemy as sa


revision = "l3f4a5b6c7d8"
down_revision = "k2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("business_document_sequences"):
        op.create_table(
            "business_document_sequences",
            sa.Column("business_id", sa.UUID(), nullable=False),
            sa.Column("document_type", sa.String(length=30), nullable=False),
            sa.Column(
                "next_number",
                sa.Integer(),
                server_default="1",
                nullable=False,
            ),
            sa.CheckConstraint(
                "next_number >= 1",
                name="ck_document_sequence_positive",
            ),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("business_id", "document_type"),
        )

    purchase_columns = {
        column["name"]
        for column in inspector.get_columns("purchases")
    }
    if "supplier_reference_number" not in purchase_columns:
        op.add_column(
            "purchases",
            sa.Column("supplier_reference_number", sa.String(length=100)),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    purchase_columns = {
        column["name"]
        for column in inspector.get_columns("purchases")
    }
    if "supplier_reference_number" in purchase_columns:
        op.drop_column("purchases", "supplier_reference_number")
    if inspector.has_table("business_document_sequences"):
        op.drop_table("business_document_sequences")
