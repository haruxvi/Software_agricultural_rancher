"""Modelo de relación usuario-predio para multitenancy."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class UserPredio(Base):
    __tablename__ = "user_predios"
    __table_args__ = (
        UniqueConstraint("user_id", "predio_id", name="uq_user_predio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    predio_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="owner"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
