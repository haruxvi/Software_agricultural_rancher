"""Tests para el servicio de render NDVI → PNG."""

import io
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from backend.services.render import ndvi_to_png

NODATA = -9999.0
BBOX = (-71.38, -34.652, -71.365, -34.64)


def _write_ndvi(path: Path, ndvi: np.ndarray) -> None:
    h, w = ndvi.shape
    transform = from_bounds(*BBOX, w, h)
    with rasterio.open(
        path, "w", driver="GTiff",
        height=h, width=w, count=1, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform, nodata=NODATA,
    ) as dst:
        dst.write(ndvi.astype(np.float32), 1)


def test_png_es_imagen_valida(tmp_path: Path) -> None:
    """El output debe ser un PNG RGBA parseable."""
    ndvi = np.full((8, 8), 0.5, dtype=np.float32)
    src = tmp_path / "ndvi.tif"
    _write_ndvi(src, ndvi)

    png_bytes, _ = ndvi_to_png(src)

    img = Image.open(io.BytesIO(png_bytes))
    assert img.format == "PNG"
    assert img.mode == "RGBA"
    assert img.size == (8, 8)


def test_png_dimensiones_correctas(tmp_path: Path) -> None:
    """Las dimensiones del PNG coinciden con el GeoTIFF."""
    ndvi = np.zeros((15, 20), dtype=np.float32)
    src = tmp_path / "ndvi.tif"
    _write_ndvi(src, ndvi)

    png_bytes, _ = ndvi_to_png(src)
    img = Image.open(io.BytesIO(png_bytes))

    assert img.size == (20, 15)  # PIL: (width, height)


def test_bbox_coincide_con_geotiff(tmp_path: Path) -> None:
    """El bbox devuelto debe coincidir con los bounds del GeoTIFF."""
    ndvi = np.full((4, 4), 0.3, dtype=np.float32)
    src = tmp_path / "ndvi.tif"
    _write_ndvi(src, ndvi)

    _, bbox = ndvi_to_png(src)
    min_lon, min_lat, max_lon, max_lat = bbox

    assert min_lon == pytest.approx(BBOX[0], abs=1e-6)
    assert min_lat == pytest.approx(BBOX[1], abs=1e-6)
    assert max_lon == pytest.approx(BBOX[2], abs=1e-6)
    assert max_lat == pytest.approx(BBOX[3], abs=1e-6)


def test_nodata_es_transparente(tmp_path: Path) -> None:
    """Píxeles nodata deben tener alpha = 0."""
    ndvi = np.array(
        [[0.5, NODATA], [NODATA, 0.8]], dtype=np.float32
    )
    src = tmp_path / "ndvi.tif"
    _write_ndvi(src, ndvi)

    png_bytes, _ = ndvi_to_png(src)
    img = Image.open(io.BytesIO(png_bytes))
    pixels = np.array(img)  # shape (H, W, 4)

    assert pixels[0, 1, 3] == 0, "nodata (0,1) debe ser transparente"
    assert pixels[1, 0, 3] == 0, "nodata (1,0) debe ser transparente"
    assert pixels[0, 0, 3] > 0, "pixel válido (0,0) debe ser opaco"
    assert pixels[1, 1, 3] > 0, "pixel válido (1,1) debe ser opaco"


def test_vegetacion_mas_verde_que_suelo(tmp_path: Path) -> None:
    """Píxel con NDVI alto debe tener canal verde mayor que uno con NDVI bajo."""
    ndvi = np.array([[0.8, 0.05]], dtype=np.float32)
    src = tmp_path / "ndvi.tif"
    _write_ndvi(src, ndvi)

    png_bytes, _ = ndvi_to_png(src)
    img = Image.open(io.BytesIO(png_bytes))
    pixels = np.array(img)  # shape (1, 2, 4) — RGBA

    green_vegetacion = int(pixels[0, 0, 1])
    green_suelo = int(pixels[0, 1, 1])
    assert green_vegetacion > green_suelo


def test_archivo_no_existe(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ndvi_to_png(tmp_path / "noexiste.tif")
