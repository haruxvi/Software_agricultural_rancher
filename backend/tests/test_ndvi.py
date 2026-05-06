"""Tests unitarios para el cálculo de NDVI (sin I/O real de Sentinel)."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.services.ndvi import NDVIStats, compute_ndvi

NODATA = -9999.0


def _write_b04b08(path: Path, b04: np.ndarray, b08: np.ndarray) -> None:
    """Escribe un GeoTIFF sintético con dos bandas."""
    h, w = b04.shape
    transform = from_bounds(-71.38, -34.652, -71.365, -34.64, w, h)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=2,
        dtype=np.float32,
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=NODATA,
    ) as dst:
        dst.write(b04.astype(np.float32), 1)
        dst.write(b08.astype(np.float32), 2)


# ---------------------------------------------------------------------------
# Casos físicos básicos
# ---------------------------------------------------------------------------

def test_ndvi_vegetacion_densa(tmp_path: Path) -> None:
    """Vegetación densa: NIR alto, rojo bajo → NDVI cercano a 1."""
    b04 = np.full((4, 4), 0.05, dtype=np.float32)
    b08 = np.full((4, 4), 0.70, dtype=np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    _, stats = compute_ndvi(src, out)

    expected = (0.70 - 0.05) / (0.70 + 0.05)  # ≈ 0.867
    assert abs(stats.mean - expected) < 1e-4
    assert stats.min == pytest.approx(expected, abs=1e-4)
    assert stats.valid_pixel_pct == pytest.approx(100.0)


def test_ndvi_suelo_desnudo(tmp_path: Path) -> None:
    """Suelo desnudo: NIR ≈ rojo → NDVI cercano a 0."""
    b04 = np.full((4, 4), 0.20, dtype=np.float32)
    b08 = np.full((4, 4), 0.22, dtype=np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    _, stats = compute_ndvi(src, out)

    expected = (0.22 - 0.20) / (0.22 + 0.20)
    assert abs(stats.mean - expected) < 1e-4
    assert stats.min >= -0.1


def test_ndvi_agua(tmp_path: Path) -> None:
    """Agua: NIR muy bajo, rojo más alto → NDVI negativo."""
    b04 = np.full((4, 4), 0.08, dtype=np.float32)
    b08 = np.full((4, 4), 0.02, dtype=np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    _, stats = compute_ndvi(src, out)

    assert stats.mean < 0.0


# ---------------------------------------------------------------------------
# Manejo de nodata y casos límite
# ---------------------------------------------------------------------------

def test_ndvi_mascara_nodata(tmp_path: Path) -> None:
    """Píxeles marcados como nodata deben quedar como nodata en el output."""
    b04 = np.array([[0.05, NODATA], [0.05, 0.05]], dtype=np.float32)
    b08 = np.array([[0.60, 0.60], [NODATA, 0.60]], dtype=np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    result_path, stats = compute_ndvi(src, out)

    with rasterio.open(result_path) as ds:
        ndvi = ds.read(1)

    # Solo el pixel (0,0) es válido; (0,1), (1,0) tienen nodata
    assert ndvi[0, 0] != NODATA
    assert ndvi[0, 1] == pytest.approx(NODATA)
    assert ndvi[1, 0] == pytest.approx(NODATA)
    assert stats.valid_pixel_pct == pytest.approx(50.0)


def test_ndvi_denominador_cero(tmp_path: Path) -> None:
    """Cuando B04 = B08 = 0, el pixel debe quedar como nodata (no NaN/inf)."""
    b04 = np.zeros((3, 3), dtype=np.float32)
    b08 = np.zeros((3, 3), dtype=np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    _, stats = compute_ndvi(src, out)

    with rasterio.open(out) as ds:
        ndvi = ds.read(1)

    assert not np.any(np.isnan(ndvi))
    assert not np.any(np.isinf(ndvi))
    assert stats.valid_pixel_pct == pytest.approx(0.0)


def test_ndvi_output_rango_valido(tmp_path: Path) -> None:
    """NDVI siempre debe estar en [-1, 1] en píxeles válidos."""
    rng = np.random.default_rng(0)
    b04 = rng.uniform(0.01, 0.30, (10, 10)).astype(np.float32)
    b08 = rng.uniform(0.05, 0.80, (10, 10)).astype(np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    _, stats = compute_ndvi(src, out)

    assert stats.min >= -1.0 - 1e-6
    assert stats.max <= 1.0 + 1e-6


# ---------------------------------------------------------------------------
# Errores esperados
# ---------------------------------------------------------------------------

def test_ndvi_archivo_no_existe(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_ndvi(tmp_path / "noexiste.tif", tmp_path / "out.tif")


def test_ndvi_bandas_incorrectas(tmp_path: Path) -> None:
    """GeoTIFF con una sola banda debe fallar con ValueError."""
    src = tmp_path / "single_band.tif"
    transform = from_bounds(-71.38, -34.652, -71.365, -34.64, 4, 4)
    with rasterio.open(
        src, "w", driver="GTiff", height=4, width=4,
        count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform,
    ) as dst:
        dst.write(np.ones((4, 4), dtype=np.float32), 1)

    with pytest.raises(ValueError, match="2 bandas"):
        compute_ndvi(src, tmp_path / "out.tif")


# ---------------------------------------------------------------------------
# Integridad del GeoTIFF generado
# ---------------------------------------------------------------------------

def test_ndvi_geotiff_metadatos(tmp_path: Path) -> None:
    """El GeoTIFF de salida conserva CRS, transform y nodata del input."""
    b04 = np.full((5, 5), 0.05, dtype=np.float32)
    b08 = np.full((5, 5), 0.50, dtype=np.float32)
    src = tmp_path / "in.tif"
    out = tmp_path / "ndvi.tif"
    _write_b04b08(src, b04, b08)

    compute_ndvi(src, out)

    with rasterio.open(src) as s, rasterio.open(out) as d:
        assert d.crs == s.crs
        assert d.transform == s.transform
        assert d.nodata == NODATA
        assert d.count == 1
