"""Tests unitarios para detección de anomalías z-score."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.services.anomaly import MIN_BASELINE_MONTHS, compute_anomaly

NODATA = -9999.0
BBOX = (-71.38, -34.652, -71.365, -34.64)


def _write_ndvi(directory: Path, date_from: date, date_to: date, value: float) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date_from}_{date_to}_NDVI.tif"
    transform = from_bounds(*BBOX, 10, 10)
    data = np.full((10, 10), value, dtype=np.float32)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=10, width=10, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(data, 1)
    return path


def _build_baseline(directory: Path, n: int = 4, base_value: float = 0.50) -> None:
    """
    Crea n meses de baseline con variación leve entre meses para que std > 0.
    Cada mes varía ±(n//2 * 0.05) alrededor de base_value.
    """
    months = [(2025, m) for m in range(1, n + 1)]
    half = n // 2
    for i, (y, m) in enumerate(months):
        value = base_value + (i - half) * 0.05
        _write_ndvi(directory, date(y, m, 1), date(y, m, 28), value)


# ── Casos físicos ──────────────────────────────────────────────────────────────

def test_zscore_negativo_cuando_ndvi_bajo(tmp_path: Path) -> None:
    """Mes con NDVI menor al baseline → z-score negativo (estrés)."""
    _build_baseline(tmp_path, n=5, base_value=0.60)
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), 0.20)

    _, stats = compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), tmp_path / "out.tif")

    assert stats.z_mean < 0
    assert stats.pct_stress > 0


def test_zscore_positivo_cuando_ndvi_alto(tmp_path: Path) -> None:
    """Mes con NDVI mayor al baseline → z-score positivo."""
    _build_baseline(tmp_path, n=5, base_value=0.25)
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), 0.85)

    _, stats = compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), tmp_path / "out.tif")

    assert stats.z_mean > 0
    assert stats.pct_above > 0


def test_zscore_cero_cuando_ndvi_igual_a_media(tmp_path: Path) -> None:
    """Mes con NDVI igual a la media del baseline → z-score ≈ 0."""
    values = [0.48, 0.50, 0.52, 0.54, 0.56]
    for i, m in enumerate(range(1, 6)):
        _write_ndvi(tmp_path, date(2025, m, 1), date(2025, m, 28), values[i])
    mean_val = sum(values) / len(values)  # 0.52
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), mean_val)

    _, stats = compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), tmp_path / "out.tif")

    assert abs(stats.z_mean) < 0.5


def test_porcentajes_suman_100(tmp_path: Path) -> None:
    """pct_stress + pct_normal + pct_above debe ser ≈ 100."""
    _build_baseline(tmp_path, n=5, base_value=0.50)
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), 0.30)

    _, stats = compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), tmp_path / "out.tif")

    total = stats.pct_stress + stats.pct_normal + stats.pct_above
    assert abs(total - 100.0) < 1e-3


# ── Nodata ─────────────────────────────────────────────────────────────────────

def test_nodata_en_target_se_propaga(tmp_path: Path) -> None:
    """Píxeles nodata en el target deben quedar nodata en el z-score."""
    _build_baseline(tmp_path, n=4, base_value=0.50)

    # Target con nodata en mitad de la imagen
    target_path = tmp_path / "2026-03-01_2026-03-31_NDVI.tif"
    transform = from_bounds(*BBOX, 10, 10)
    data = np.full((10, 10), 0.30, dtype=np.float32)
    data[:, 5:] = NODATA  # mitad derecha = nodata
    with rasterio.open(
        target_path, "w", driver="GTiff",
        height=10, width=10, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(data, 1)

    out = tmp_path / "out.tif"
    compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), out)

    with rasterio.open(out) as ds:
        zscore = ds.read(1)

    assert np.all(zscore[:, 5:] == NODATA)
    assert not np.any(zscore[:, :5] == NODATA)


def test_std_cero_queda_nodata(tmp_path: Path) -> None:
    """Píxeles con std=0 (baseline exactamente igual) deben quedar nodata."""
    for m in range(1, 6):
        _write_ndvi(tmp_path, date(2025, m, 1), date(2025, m, 28), 0.50)  # uniforme → std=0
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), 0.30)

    out = tmp_path / "out.tif"
    compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), out)

    with rasterio.open(out) as ds:
        zscore = ds.read(1)

    # std≈0 → todos nodata
    assert np.all(zscore == NODATA)


# ── Errores esperados ──────────────────────────────────────────────────────────

def test_falla_sin_archivo_objetivo(tmp_path: Path) -> None:
    _build_baseline(tmp_path, n=4)
    with pytest.raises(FileNotFoundError, match="GeoTIFF objetivo"):
        compute_anomaly(tmp_path, date(2026, 6, 1), date(2026, 6, 30), tmp_path / "out.tif")


def test_falla_con_pocos_meses_baseline(tmp_path: Path) -> None:
    _build_baseline(tmp_path, n=MIN_BASELINE_MONTHS - 1)
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), 0.40)
    with pytest.raises(ValueError, match="baseline"):
        compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), tmp_path / "out.tif")


# ── Integridad del GeoTIFF ─────────────────────────────────────────────────────

def test_geotiff_output_metadatos(tmp_path: Path) -> None:
    """El GeoTIFF z-score debe conservar CRS, transform y nodata."""
    _build_baseline(tmp_path, n=4)
    _write_ndvi(tmp_path, date(2026, 3, 1), date(2026, 3, 31), 0.30)
    out = tmp_path / "out.tif"

    compute_anomaly(tmp_path, date(2026, 3, 1), date(2026, 3, 31), out)

    with rasterio.open(tmp_path / "2026-03-01_2026-03-31_NDVI.tif") as src, \
         rasterio.open(out) as dst:
        assert dst.crs == src.crs
        assert dst.transform == src.transform
        assert dst.nodata == NODATA
        assert dst.count == 1
