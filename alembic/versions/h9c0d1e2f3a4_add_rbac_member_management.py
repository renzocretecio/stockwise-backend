"""add RBAC member management

Revision ID: h9c0d1e2f3a4
Revises: g8b9c0d1e2f3
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config.rbac import (
    PERMISSIONS,
    SYSTEM_ROLE_DESCRIPTIONS,
    SYSTEM_ROLE_PERMISSIONS,
)


revision = "h9c0d1e2f3a4"
down_revision = "g8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_roles_business_lower_name
        ON roles (business_id, lower(name))
        WHERE business_id IS NOT NULL
        """
    )
    if not inspector.has_table("business_invitations"):
        op.create_table(
            "business_invitations",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column(
                "business_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column(
                "role_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column(
                "invited_by",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "status",
                sa.String(length=30),
                server_default="pending",
                nullable=False,
            ),
            sa.Column(
                "expires_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column(
                "accepted_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.CheckConstraint(
                "status IN ('pending', 'accepted', 'revoked', 'expired')",
                name="ck_business_invitations_status",
            ),
            sa.ForeignKeyConstraint(
                ["business_id"],
                ["businesses.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["role_id"],
                ["roles.id"],
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["invited_by"],
                ["users.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        existing_indexes: set[str] = set()
    else:
        existing_indexes = {
            index["name"] for index in inspector.get_indexes("business_invitations")
        }
        check_constraints = {
            constraint["name"]
            for constraint in inspector.get_check_constraints("business_invitations")
        }
        if "ck_business_invitations_status" not in check_constraints:
            op.create_check_constraint(
                "ck_business_invitations_status",
                "business_invitations",
                "status IN ('pending', 'accepted', 'revoked', 'expired')",
            )

    invitation_indexes = (
        (
            "ix_business_invitations_business_id",
            ["business_id"],
            False,
            None,
        ),
        ("ix_business_invitations_email", ["email"], False, None),
        (
            "ix_business_invitations_token_hash",
            ["token_hash"],
            True,
            None,
        ),
        (
            "uq_pending_business_invitation_email",
            ["business_id", "email"],
            True,
            sa.text("status = 'pending'"),
        ),
    )
    for name, columns, unique, where_clause in invitation_indexes:
        if name not in existing_indexes:
            op.create_index(
                name,
                "business_invitations",
                columns,
                unique=unique,
                postgresql_where=where_clause,
            )

    permission_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("key", sa.String()),
        sa.column("description", sa.String()),
    )
    for key, description in PERMISSIONS.items():
        op.execute(
            postgresql.insert(permission_table)
            .values(
                id=sa.text("gen_random_uuid()"),
                key=key,
                description=description,
            )
            .on_conflict_do_update(
                index_elements=["key"],
                set_={"description": description},
            )
        )

    for role_name, description in SYSTEM_ROLE_DESCRIPTIONS.items():
        op.execute(
            sa.text(
                """
                INSERT INTO roles (
                    id, business_id, name, description, is_system_role
                )
                SELECT
                    gen_random_uuid(), b.id, :name, :description, TRUE
                FROM businesses b
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM roles r
                    WHERE r.business_id = b.id
                      AND lower(r.name) = :name
                )
                """
            ).bindparams(name=role_name, description=description)
        )

    op.execute(
        """
        UPDATE business_memberships bm
        SET role_id = business_role.id
        FROM roles old_role, roles business_role
        WHERE bm.role_id = old_role.id
          AND old_role.business_id IS NULL
          AND business_role.business_id = bm.business_id
          AND lower(business_role.name) = CASE
              WHEN lower(old_role.name) = 'clerk' THEN 'cashier'
              ELSE lower(old_role.name)
          END
        """
    )

    for role_name, permission_keys in SYSTEM_ROLE_PERMISSIONS.items():
        op.execute(
            sa.text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT r.id, p.id
                FROM roles r
                JOIN permissions p ON p.key = ANY(:permission_keys)
                WHERE lower(r.name) = :role_name
                  AND (
                      r.business_id IS NOT NULL
                      OR r.is_system_role = TRUE
                  )
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ).bindparams(
                role_name=role_name,
                permission_keys=list(permission_keys),
            )
        )


def downgrade() -> None:
    op.drop_index(
        "uq_pending_business_invitation_email",
        table_name="business_invitations",
    )
    op.drop_index(
        "ix_business_invitations_token_hash",
        table_name="business_invitations",
    )
    op.drop_index(
        "ix_business_invitations_email",
        table_name="business_invitations",
    )
    op.drop_index(
        "ix_business_invitations_business_id",
        table_name="business_invitations",
    )
    op.drop_table("business_invitations")
    op.execute("DROP INDEX IF EXISTS uq_roles_business_lower_name")
