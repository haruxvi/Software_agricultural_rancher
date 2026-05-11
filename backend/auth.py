import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import get_db

logger = logging.getLogger(__name__)

# auto_error=False para manejar manualmente el caso sin credenciales
_bearer = HTTPBearer(auto_error=False)

# Regex de validación para predio_id — previene path traversal
_PREDIO_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Valida JWT emitido por Supabase. Solo en development sin secret retorna usuario ficticio."""
    if not settings.supabase_jwt_secret:
        if settings.environment == "development":
            return {"sub": "dev-user", "email": "dev@local", "role": "authenticated"}
        logger.critical(
            "SUPABASE_JWT_SECRET no configurado en entorno '%s'", settings.environment
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servicio mal configurado",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except JWTError as exc:
        logger.warning("JWT inválido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_user_predio(
    predio_id: Annotated[str, Path(pattern=_PREDIO_PATTERN)],
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> str:
    """Valida que el usuario tenga acceso al predio. En dev, omite validación."""
    if not settings.supabase_jwt_secret:
        # Modo desarrollo — sin BD de ownership
        return predio_id

    from backend.services.authorization import user_owns_predio

    if not user_owns_predio(db, user["sub"], predio_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este predio",
        )
    return predio_id
