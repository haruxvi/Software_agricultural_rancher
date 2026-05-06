"""Conversión de GeoTIFFs (NDVI y z-score) a PNG RGBA para overlay en Leaflet."""

import io
import logging
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image

logger = logging.getLogger(__name__)

_CMAP_NDVI    = colormaps["RdYlGn"]   # NDVI: rojo → amarillo → verde
_CMAP_ANOMALY = colormaps["RdBu"]     # Anomalía: rojo=estrés, azul=sobre lo normal

NDVI_MIN = -1.0
NDVI_MAX = 1.0
ZSCORE_CLIP = 3.0  # z-scores fuera de [-3, 3] se saturan en el colormap


def ndvi_to_png(ndvi_path: Path) -> tuple[bytes, tuple[float, float, float, float]]:
    """
    Lee un GeoTIFF NDVI y devuelve un PNG RGBA coloreado + el bbox geográfico.

    El colormap RdYlGn mapea:
        NDVI ≤ 0   → rojo   (agua, nubes residuales)
        NDVI ~ 0.3 → amarillo (vegetación escasa / suelo)
        NDVI ≥ 0.6 → verde   (vegetación densa / viña sana)

    Píxeles con nodata quedan transparentes (alpha = 0).

    Args:
        ndvi_path: ruta al GeoTIFF NDVI de una sola banda.

    Returns:
        (png_bytes, (min_lon, min_lat, max_lon, max_lat))

    Raises:
        FileNotFoundError: si ndvi_path no existe.
    """
    if not ndvi_path.exists():
        raise FileNotFoundError(f"GeoTIFF NDVI no encontrado: {ndvi_path}")

    with rasterio.open(ndvi_path) as src:
        ndvi = src.read(1).astype(np.float32)
        nodata_val: float = src.nodata if src.nodata is not None else -9999.0
        bounds = src.bounds  # BoundingBox(left, bottom, right, top)

    valid = ndvi != nodata_val

    # Normalizar [-1, 1] → [0, 1] para el colormap
    normalized = np.zeros_like(ndvi)
    normalized[valid] = np.clip(
        (ndvi[valid] - NDVI_MIN) / (NDVI_MAX - NDVI_MIN), 0.0, 1.0
    )

    rgba = _CMAP_NDVI(normalized)

    # Píxeles nodata → completamente transparentes
    rgba[~valid, 3] = 0.0

    rgba_uint8 = (rgba * 255).astype(np.uint8)
    img = Image.fromarray(rgba_uint8, mode="RGBA")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    buf.seek(0)
    png_bytes = buf.read()

    bbox = (bounds.left, bounds.bottom, bounds.right, bounds.top)
    logger.info(
        "PNG generado | %dx%d px | %.1f KB | bbox=%s",
        img.width,
        img.height,
        len(png_bytes) / 1024,
        bbox,
    )
    return png_bytes, bbox


def zscore_to_png(zscore_path: Path) -> tuple[bytes, tuple[float, float, float, float]]:
    """
    Lee un GeoTIFF z-score y devuelve un PNG RGBA coloreado + el bbox geográfico.

    Colormap RdBu (divergente centrado en 0):
        z ≤ -3  → rojo intenso   (estrés severo)
        z =  0  → blanco         (normal)
        z ≥ +3  → azul intenso   (sobre lo normal)

    Args:
        zscore_path: ruta al GeoTIFF de z-scores de una sola banda.

    Returns:
        (png_bytes, (min_lon, min_lat, max_lon, max_lat))

    Raises:
        FileNotFoundError: si zscore_path no existe.
    """
    if not zscore_path.exists():
        raise FileNotFoundError(f"GeoTIFF z-score no encontrado: {zscore_path}")

    with rasterio.open(zscore_path) as src:
        zscore = src.read(1).astype(np.float32)
        nodata_val: float = src.nodata if src.nodata is not None else -9999.0
        bounds = src.bounds

    valid = zscore != nodata_val

    # Normalizar [-ZSCORE_CLIP, +ZSCORE_CLIP] → [0, 1]
    normalized = np.full_like(zscore, 0.5)  # neutro para nodata
    normalized[valid] = np.clip(
        (zscore[valid] + ZSCORE_CLIP) / (2 * ZSCORE_CLIP), 0.0, 1.0
    )

    rgba = _CMAP_ANOMALY(normalized)
    rgba[~valid, 3] = 0.0

    rgba_uint8 = (rgba * 255).astype(np.uint8)
    img = Image.fromarray(rgba_uint8, mode="RGBA")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    buf.seek(0)
    png_bytes = buf.read()

    bbox = (bounds.left, bounds.bottom, bounds.right, bounds.top)
    logger.info(
        "Anomaly PNG generado | %dx%d px | %.1f KB",
        img.width, img.height, len(png_bytes) / 1024,
    )
    return png_bytes, bbox
