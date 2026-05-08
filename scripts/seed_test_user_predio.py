"""Inserta UserPredio de prueba para SUPABASE_TEST_USER_ID → predio_prueba."""

import os
import sys
import uuid

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.user_predio import UserPredio

PREDIO_ID = "predio_prueba"


def seed() -> None:
    raw_id = os.environ.get("SUPABASE_TEST_USER_ID")
    if not raw_id:
        print("ERROR: SUPABASE_TEST_USER_ID no está definido en el entorno", file=sys.stderr)
        sys.exit(1)

    try:
        user_uuid = uuid.UUID(raw_id)
    except ValueError:
        print(f"ERROR: SUPABASE_TEST_USER_ID no es UUID válido: {raw_id!r}", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        existing = db.execute(
            select(UserPredio).where(
                UserPredio.user_id == user_uuid,
                UserPredio.predio_id == PREDIO_ID,
            )
        ).scalar_one_or_none()

        if existing:
            print(f"Ya existe: user_id={raw_id}, predio_id={PREDIO_ID}")
            return

        db.add(UserPredio(user_id=user_uuid, predio_id=PREDIO_ID, role="owner"))
        db.commit()
        print(f"Creado: user_id={raw_id}, predio_id={PREDIO_ID}, role=owner")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
