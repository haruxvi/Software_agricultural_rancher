"""Tests para la generación del PDF de reporte."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.services.report import build_report

BBOX = (-71.38, -34.652, -71.365, -34.64)
NODATA = -9999.0


def _write_ndvi(directory: Path, date_from: date, date_to: date,
                mean: float, suffix: str = "_NDVI.tif") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date_from}_{date_to}{suffix}"
    transform = from_bounds(*BBOX, 20, 18)
    data = np.full((18, 20), mean, dtype=np.float32)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=18, width=20, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(
            ndvi_mean=f"{mean:.4f}",
            ndvi_min=f"{mean - 0.05:.4f}",
            ndvi_max=f"{mean + 0.05:.4f}",
            ndvi_std="0.0500",
            ndvi_valid_pixel_pct="95.00",
            band_1="NDVI",
        )
    return path


def _write_zscore(directory: Path, date_from: date, date_to: date) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date_from}_{date_to}_zscore.tif"
    transform = from_bounds(*BBOX, 20, 18)
    data = np.linspace(-2.5, 2.5, 20 * 18, dtype=np.float32).reshape(18, 20)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=18, width=20, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(data, 1)
        dst.update_tags(
            pct_stress="15.00",
            pct_normal="75.00",
            pct_above="10.00",
            baseline_months="11",
            threshold="2.0",
        )
    return path


def _write_geojson(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "nombre": "Viña Test", "region": "VI",
                "comuna": "Santa Cruz", "hectareas": 45.2, "cultivo": "vid",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [-71.38, -34.64], [-71.365, -34.64],
                    [-71.365, -34.652], [-71.38, -34.652], [-71.38, -34.64],
                ]],
            },
        }],
    }
    path.write_text(json.dumps(geojson))


def test_pdf_genera_bytes_validos(tmp_path: Path) -> None:
    """El PDF generado debe comenzar con la cabecera PDF correcta."""
    d_from, d_to = date(2026, 3, 1), date(2026, 3, 31)
    ndvi_dir    = tmp_path / "ndvi" / "predio_test"
    anomaly_dir = tmp_path / "anomaly"
    predios_dir = tmp_path / "predios"

    _write_ndvi(ndvi_dir, d_from, d_to, mean=0.55)
    _write_zscore(tmp_path / "anomaly" / "predio_test", d_from, d_to)
    _write_geojson(predios_dir / "predio_test.geojson")

    # Baseline meses para serie temporal
    for m in range(1, 6):
        _write_ndvi(ndvi_dir, date(2025, m, 1), date(2025, m, 28), mean=0.45 + m * 0.02)

    pdf_bytes = build_report(
        predio_id="predio_test",
        date_from=d_from,
        date_to=d_to,
        ndvi_dir=tmp_path / "ndvi",
        anomaly_dir=anomaly_dir,
        predios_dir=predios_dir,
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF", "Los bytes deben comenzar con la cabecera PDF"
    assert len(pdf_bytes) > 5_000, "PDF demasiado pequeño — posible error de generación"


def test_pdf_sin_ndvi_lanza_error(tmp_path: Path) -> None:
    """Si no existe el GeoTIFF NDVI debe lanzar FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="GeoTIFF NDVI"):
        build_report(
            predio_id="no_existe",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 3, 31),
            ndvi_dir=tmp_path / "ndvi",
            anomaly_dir=tmp_path / "anomaly",
            predios_dir=tmp_path / "predios",
        )


def test_pdf_sin_anomalia_funciona(tmp_path: Path) -> None:
    """El PDF debe generarse aunque no haya datos de anomalía."""
    d_from, d_to = date(2026, 3, 1), date(2026, 3, 31)
    ndvi_dir    = tmp_path / "ndvi" / "predio_test"
    _write_ndvi(ndvi_dir, d_from, d_to, mean=0.52)
    _write_geojson(tmp_path / "predios" / "predio_test.geojson")

    pdf_bytes = build_report(
        predio_id="predio_test",
        date_from=d_from,
        date_to=d_to,
        ndvi_dir=tmp_path / "ndvi",
        anomaly_dir=tmp_path / "anomaly",  # directorio vacío
        predios_dir=tmp_path / "predios",
    )

    assert pdf_bytes[:4] == b"%PDF"
