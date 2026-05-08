"""Servicio de autorización: verifica ownership de predios."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.user_predio import UserPredio

logger = logging.getLogger(__name__)


def user_owns_predio(db: Session, user_id: str, predio_id: str) -> bool:
    """Devuelve True si user_id tiene un registro de ownership sobre predio_id."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.warning("user_id no es UUID válido: %s", user_id)
        return False

    row = db.execute(
        select(UserPredio).where(
            UserPredio.user_id == uid,
            UserPredio.predio_id == predio_id,
        )
    ).scalar_one_or_none()
    return row is not None
