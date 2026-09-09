"""add idempotency request records

Revision ID: bc23de45fa67
Revises: aa12bc34de56
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "bc23de45fa67"
down_revision = "aa12bc34de56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "idempotency_requests" not in inspector.get_table_names():
        op.create_table(
            "idempotency_requests",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("request_scope", sa.String(128), nullable=False),
            sa.Column("idempotency_key", sa.String(255), nullable=False),
            sa.Column("request_fingerprint", sa.String(64), nullable=False),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("response_body", sa.Text(), nullable=True),
            sa.Column("response_content_type", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "request_scope",
                "idempotency_key",
                name="uq_idempotency_request_scope_key",
            ),
        )
    if "ix_idempotency_requests_created_at" not in {
        index["name"] for index in inspector.get_indexes("idempotency_requests")
    }:
        op.create_index(
            "ix_idempotency_requests_created_at",
            "idempotency_requests",
            ["created_at"],
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "idempotency_requests" in inspector.get_table_names():
        if "ix_idempotency_requests_created_at" in {
            index["name"] for index in inspector.get_indexes("idempotency_requests")
        }:
            op.drop_index(
                "ix_idempotency_requests_created_at",
                table_name="idempotency_requests",
            )
        op.drop_table("idempotency_requests")