"""Tests de control de acceso por recurso (multitenancy / IDOR)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt
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


# ── Fail-closed y validaciones JWT ───────────────────────────────────────────


def test_prod_sin_secrets_falla_al_arrancar(monkeypatch):
    """Settings no arranca en production sin secrets obligatorios → ValidationError."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    from pydantic import ValidationError

    from backend.config import Settings

    with pytest.raises(ValidationError, match="requeridas en producción"):
        Settings(_env_file=None)


def test_prod_con_secret_sin_token_401(monkeypatch):
    """En production con secret configurado, sin token → 401 (nunca fake user)."""
    monkeypatch.setattr(settings, "environment", "production")
    resp = TestClient(app).get(ENDPOINT)
    assert resp.status_code == 401


def test_token_sub_vacio_401(monkeypatch):
    """Token válido pero con sub vacío → 401."""
    monkeypatch.setattr(settings, "supabase_url", "")
    token = jose_jwt.encode(
        {"sub": "", "aud": "authenticated"},
        "test-secret",
        algorithm="HS256",
    )
    resp = TestClient(app).get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_token_issuer_incorrecto_401(monkeypatch):
    """Token con issuer distinto al esperado → 401."""
    monkeypatch.setattr(settings, "supabase_url", "https://myproject.supabase.co")
    token = jose_jwt.encode(
        {
            "sub": OWNER_ID,
            "aud": "authenticated",
            "iss": "https://intruder.supabase.co/auth/v1",
        },
        "test-secret",
        algorithm="HS256",
    )
    resp = TestClient(app).get(ENDPOINT, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
