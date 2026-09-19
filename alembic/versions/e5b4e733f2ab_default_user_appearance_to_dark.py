"""default user appearance to dark

Revision ID: e5b4e733f2ab
Revises: q8e9f0a1b2c3
Create Date: 2026-09-19 20:45:04.130051

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5b4e733f2ab"
down_revision: Union[str, None] = "q8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "appearance_mode",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        server_default="dark",
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "appearance_mode",
        existing_type=sa.String(length=10),
        existing_nullable=False,
        server_default="system",
    )
