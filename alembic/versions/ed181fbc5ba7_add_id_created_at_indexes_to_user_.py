"""add id created_at indexes to user_predios

Revision ID: ed181fbc5ba7
Revises: 001
Create Date: 2026-05-07 14:17:11.628757
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = 'ed181fbc5ba7'
down_revision: str | None = '001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Reemplaza la tabla con PK compuesta por una con id UUID propio,
    # indexes individuales y constraint UNIQUE en (user_id, predio_id).
    op.drop_table("user_predios")
    op.create_table(
        "user_predios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("predio_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="owner"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "predio_id", name="uq_user_predio"),
    )
    op.create_index("ix_user_predios_user_id", "user_predios", ["user_id"])
    op.create_index("ix_user_predios_predio_id", "user_predios", ["predio_id"])


def downgrade() -> None:
    op.drop_index("ix_user_predios_predio_id", table_name="user_predios")
    op.drop_index("ix_user_predios_user_id", table_name="user_predios")
    op.drop_table("user_predios")
    op.create_table(
        "user_predios",
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("predio_id", sa.Text(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="owner"),
        sa.PrimaryKeyConstraint("user_id", "predio_id"),
    )
