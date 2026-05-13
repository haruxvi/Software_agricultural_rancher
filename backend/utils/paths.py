from pathlib import Path

from fastapi import HTTPException


def safe_data_path(base: Path, *parts: str) -> Path:
    """Construye una ruta dentro de base, validando que no escape via traversal."""
    base = base.resolve()
    candidate = base.joinpath(*parts).resolve()
    if not candidate.is_relative_to(base):
        raise HTTPException(status_code=400, detail="Ruta inválida")
    return candidate
