"""add report export permission

Revision ID: i0d1e2f3a4b5
Revises: h9c0d1e2f3a4
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "i0d1e2f3a4b5"
down_revision = "h9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO permissions (id, key, description, created_at)
        VALUES (
            gen_random_uuid(),
            'reports.export',
            'Export report and dashboard data',
            now()
        )
        ON CONFLICT (key) DO UPDATE
        SET description = EXCLUDED.description
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.key = 'reports.export'
        WHERE lower(r.name) IN ('owner', 'manager')
          AND (r.business_id IS NOT NULL OR r.is_system_role = TRUE)
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN (
                SELECT id FROM permissions WHERE key = 'reports.export'
            )
            """
        )
    )
    op.execute("DELETE FROM permissions WHERE key = 'reports.export'")
