"""add ordered purchase status

Revision ID: c93d071e5b24
Revises: b482f0a713de
Create Date: 2026-08-28
"""

from alembic import op
import sqlalchemy as sa


revision = "c93d071e5b24"
down_revision = "b482f0a713de"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchases", sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("purchases", sa.Column("ordered_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_purchases_ordered_by_users",
        "purchases",
        "users",
        ["ordered_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("ck_purchases_status", "purchases", type_="check")
    op.create_check_constraint(
        "ck_purchases_status",
        "purchases",
        "status IN ('draft', 'ordered', 'received', 'cancelled')",
    )


def downgrade() -> None:
    op.execute("UPDATE purchases SET status = 'draft' WHERE status = 'ordered'")
    op.drop_constraint("ck_purchases_status", "purchases", type_="check")
    op.create_check_constraint(
        "ck_purchases_status",
        "purchases",
        "status IN ('draft', 'received', 'cancelled')",
    )
    op.drop_constraint("fk_purchases_ordered_by_users", "purchases", type_="foreignkey")
    op.drop_column("purchases", "ordered_by")
    op.drop_column("purchases", "ordered_at")
