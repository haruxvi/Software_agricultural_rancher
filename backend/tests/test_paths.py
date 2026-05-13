"""Tests unitarios para backend.utils.paths.safe_data_path."""

import pytest
from fastapi import HTTPException

from backend.utils.paths import safe_data_path


def test_ruta_valida_simple(tmp_path):
    result = safe_data_path(tmp_path, "archivo.tif")
    assert result == (tmp_path / "archivo.tif").resolve()


def test_ruta_valida_anidada(tmp_path):
    result = safe_data_path(tmp_path, "predio1", "2024-01-01_2024-01-31_NDVI.tif")
    expected = (tmp_path / "predio1" / "2024-01-01_2024-01-31_NDVI.tif").resolve()
    assert result == expected


def test_traversal_parent_lanza_400(tmp_path):
    with pytest.raises(HTTPException) as exc_info:
        safe_data_path(tmp_path, "..", "etc", "passwd")
    assert exc_info.value.status_code == 400


def test_traversal_oculto_lanza_400(tmp_path):
    with pytest.raises(HTTPException) as exc_info:
        safe_data_path(tmp_path, "subdir", "..", "..", "secreto.txt")
    assert exc_info.value.status_code == 400


def test_ruta_absoluta_como_parte_lanza_400(tmp_path):
    import platform
    # Construye una ruta absoluta fuera de tmp_path según el SO
    if platform.system() == "Windows":
        ruta_externa = "C:\\Windows\\System32"
    else:
        ruta_externa = "/etc/passwd"
    with pytest.raises(HTTPException) as exc_info:
        safe_data_path(tmp_path, ruta_externa)
    assert exc_info.value.status_code == 400


def test_ruta_dentro_de_subdirectorio_ok(tmp_path):
    result = safe_data_path(tmp_path, "a", "b", "c.txt")
    assert str(result).startswith(str(tmp_path.resolve()))
