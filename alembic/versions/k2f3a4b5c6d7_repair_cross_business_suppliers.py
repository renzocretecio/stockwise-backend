"""repair cross-business product supplier references

Revision ID: k2f3a4b5c6d7
Revises: j1e2f3a4b5c6
Create Date: 2026-09-10
"""

from alembic import op


revision = "k2f3a4b5c6d7"
down_revision = "j1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A supplier from another business must never become a purchasing option.
    # There is no safe supplier to infer, so clear only the invalid legacy FK.
    op.execute(
        """
        UPDATE products p
        SET supplier_id = NULL,
            updated_at = now()
        WHERE p.supplier_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM suppliers s
              WHERE s.id = p.supplier_id
                AND s.business_id = p.business_id
          )
        """
    )


def downgrade() -> None:
    # Cross-business relationships are intentionally not restored.
    pass
