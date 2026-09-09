"""add user pro trial marker

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    if "pro_trial_used_at" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "pro_trial_used_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    op.execute(
        sa.text(
            """
            UPDATE users
            SET pro_trial_used_at = trial_history.first_trial_started_at
            FROM (
                SELECT
                    business_memberships.user_id,
                    MIN(business_subscriptions.trial_started_at)
                        AS first_trial_started_at
                FROM business_memberships
                JOIN roles
                    ON roles.id = business_memberships.role_id
                JOIN business_subscriptions
                    ON business_subscriptions.business_id =
                        business_memberships.business_id
                WHERE LOWER(roles.name) = 'owner'
                    AND business_subscriptions.trial_started_at IS NOT NULL
                GROUP BY business_memberships.user_id
            ) AS trial_history
            WHERE users.id = trial_history.user_id
                AND users.pro_trial_used_at IS NULL
            """
        )
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    if "pro_trial_used_at" in columns:
        op.drop_column("users", "pro_trial_used_at")
