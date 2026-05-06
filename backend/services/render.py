"""Conversión de GeoTIFF NDVI a PNG RGBA para overlay en Leaflet."""

import io
import logging
from pathlib import Path

import numpy as np
import rasterio
from matplotlib import colormaps
from PIL import Image

logger = logging.getLogger(__name__)

# Colormap estándar para NDVI: rojo (bajo) → amarillo → verde (alto)
_CMAP = colormaps["RdYlGn"]

# Rango físico de NDVI para normalización
NDVI_MIN = -1.0
NDVI_MAX = 1.0


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

    # Aplicar colormap: output shape (H, W, 4) en [0, 1]
    rgba = _CMAP(normalized)

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
