"""Tests para el servicio de serie temporal NDVI."""

import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.services.timeseries import read_timeseries


def _write_ndvi_tif(path: Path, mean: float, min_: float, max_: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(-71.38, -34.652, -71.365, -34.64, 10, 10)
    data = np.full((10, 10), mean, dtype=np.float32)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=10, width=10, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=-9999,
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(
            ndvi_mean=f"{mean:.4f}",
            ndvi_min=f"{min_:.4f}",
            ndvi_max=f"{max_:.4f}",
            ndvi_std="0.0500",
            ndvi_valid_pixel_pct="95.00",
        )


def test_retorna_lista_vacia_si_no_hay_directorio(tmp_path: Path) -> None:
    result = read_timeseries(tmp_path / "no_existe")
    assert result == []


def test_retorna_lista_vacia_si_directorio_sin_tifs(tmp_path: Path) -> None:
    (tmp_path / "predio").mkdir()
    result = read_timeseries(tmp_path / "predio")
    assert result == []


def test_lee_un_archivo_correctamente(tmp_path: Path) -> None:
    tif = tmp_path / "2026-03-01_2026-03-31_NDVI.tif"
    _write_ndvi_tif(tif, mean=0.55, min_=0.20, max_=0.82)

    result = read_timeseries(tmp_path)

    assert len(result) == 1
    assert result[0].date_from == date(2026, 3, 1)
    assert result[0].date_to == date(2026, 3, 31)
    assert result[0].mean == pytest.approx(0.55, abs=1e-3)
    assert result[0].valid_pixel_pct == pytest.approx(95.0, abs=0.1)


def test_ordena_por_fecha_ascendente(tmp_path: Path) -> None:
    for month, mean in [(6, 0.15), (1, 0.68), (3, 0.53), (11, 0.48)]:
        tif = tmp_path / f"2026-{month:02d}-01_2026-{month:02d}-28_NDVI.tif"
        _write_ndvi_tif(tif, mean=mean, min_=mean - 0.1, max_=mean + 0.1)

    result = read_timeseries(tmp_path)

    assert len(result) == 4
    dates = [p.date_from.month for p in result]
    assert dates == sorted(dates)


def test_ignora_archivos_con_nombre_incorrecto(tmp_path: Path) -> None:
    # Archivo válido
    _write_ndvi_tif(tmp_path / "2026-03-01_2026-03-31_NDVI.tif", 0.5, 0.2, 0.8)
    # Archivos que deben ignorarse
    (tmp_path / "README.txt").write_text("ignore")
    (tmp_path / "mal_nombre.tif").write_text("")
    (tmp_path / "2026-03_NDVI.tif").write_text("")

    result = read_timeseries(tmp_path)
    assert len(result) == 1


def test_tolera_tags_faltantes(tmp_path: Path) -> None:
    """GeoTIFF sin tags NDVI debe incluirse con NaN, no lanzar excepción."""
    path = tmp_path / "2026-04-01_2026-04-30_NDVI.tif"
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(-71.38, -34.652, -71.365, -34.64, 5, 5)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=5, width=5, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=-9999,
    ) as dst:
        dst.write(np.zeros((5, 5), dtype=np.float32), 1)
        # Sin tags NDVI

    result = read_timeseries(tmp_path)
    assert len(result) == 1
    assert math.isnan(result[0].mean)
