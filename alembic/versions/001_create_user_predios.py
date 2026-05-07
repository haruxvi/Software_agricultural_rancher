"""create user_predios table

Revision ID: 001
Revises:
Create Date: 2026-05-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_predios",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("predio_id", sa.Text(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="owner"),
        sa.PrimaryKeyConstraint("user_id", "predio_id"),
    )


def downgrade() -> None:
    op.drop_table("user_predios")
