"""insert roles data

Revision ID: e3878d300632
Revises: 
Create Date: 2026-08-12 17:58:59.848849

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3878d300632"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO roles (
            name,
            description,
            is_system_role
        )
        VALUES
        (
            'owner',
            'Full access to the business',
            TRUE
        ),
        (
            'manager',
            'Inventory, sales, purchases, suppliers, and reports',
            TRUE
        ),
        (
            'clerk',
            'Sales and limited inventory access',
            TRUE
        );
        """
    )


def downgrade() -> None:
        op.execute(
                """
                DELETE FROM roles r
                USING (VALUES
                        ('owner', 'Full access to the business', TRUE),
                        ('manager', 'Inventory, sales, purchases, suppliers, and reports', TRUE),
                        ('clerk', 'Sales and limited inventory access', TRUE)
                ) AS v(name, description, is_system_role)
                WHERE r.name = v.name
                    AND r.description = v.description
                    AND r.is_system_role = v.is_system_role
                    AND r.business_id IS NULL;
                """
        )
