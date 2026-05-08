"""Tests de control de acceso por recurso (multitenancy / IDOR)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth import get_current_user
from backend.config import settings
from backend.db import Base, get_db
from backend.main import app
from backend.models.user_predio import UserPredio

OWNER_ID = str(uuid.uuid4())
OTHER_ID = str(uuid.uuid4())

# StaticPool mantiene una única conexión → la BD en memoria persiste entre sesiones
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

ENDPOINT = "/ndvi/predios/predio_prueba/timeseries"


def _override_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    """Tabla user_predios en SQLite + JWT secret activo para todos los tests del módulo."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", "test-secret")
    Base.metadata.create_all(_engine)
    db = _Session()
    db.add(UserPredio(user_id=uuid.UUID(OWNER_ID), predio_id="predio_prueba", role="owner"))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(_engine)
    app.dependency_overrides.clear()


def test_owner_accede_200():
    """Usuario dueño accede a su predio → 200."""
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"sub": OWNER_ID}
    resp = TestClient(app).get(ENDPOINT)
    assert resp.status_code == 200


def test_sin_ownership_403():
    """Usuario logueado pero sin ownership → 403."""
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: {"sub": OTHER_ID}
    resp = TestClient(app).get(ENDPOINT)
    assert resp.status_code == 403


def test_sin_token_401():
    """Sin token → 401."""
    resp = TestClient(app).get(ENDPOINT)
    assert resp.status_code == 401
