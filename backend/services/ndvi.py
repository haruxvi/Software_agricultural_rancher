"""Cálculo de NDVI a partir de bandas B04/B08 en GeoTIFF."""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NDVIStats:
    mean: float
    min: float
    max: float
    std: float
    valid_pixel_pct: float  # % de píxeles sin nodata


def compute_ndvi(input_path: Path, output_path: Path) -> tuple[Path, NDVIStats]:
    """
    Calcula NDVI = (B08 - B04) / (B08 + B04) desde un GeoTIFF de dos bandas.

    Banda 1 = B04 (rojo), banda 2 = B08 (NIR).
    Píxeles con nodata o denominador cero quedan como nodata en el output.

    Args:
        input_path: GeoTIFF con B04 (banda 1) y B08 (banda 2).
        output_path: ruta del GeoTIFF NDVI resultante.

    Returns:
        (output_path, NDVIStats) con estadísticas sobre píxeles válidos.

    Raises:
        FileNotFoundError: si input_path no existe.
        ValueError: si el GeoTIFF no tiene exactamente 2 bandas.
    """
    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de bandas: {input_path}")

    with rasterio.open(input_path) as src:
        if src.count != 2:
            raise ValueError(
                f"Se esperan 2 bandas (B04, B08), el archivo tiene {src.count}"
            )
        nodata_val: float = src.nodata if src.nodata is not None else -9999.0
        b04 = src.read(1).astype(np.float32)
        b08 = src.read(2).astype(np.float32)
        profile = src.profile.copy()

    # Máscara de píxeles válidos
    valid = (b04 != nodata_val) & (b08 != nodata_val)
    denominator = b08 + b04
    # Evitar división por cero (reflectancias ambas = 0, p.ej. agua muy oscura)
    computable = valid & (denominator != 0.0)

    ndvi = np.full_like(b04, fill_value=nodata_val)
    ndvi[computable] = (b08[computable] - b04[computable]) / denominator[computable]

    # Estadísticas solo sobre píxeles computables
    valid_values = ndvi[computable]
    stats = NDVIStats(
        mean=float(np.mean(valid_values)) if valid_values.size > 0 else float("nan"),
        min=float(np.min(valid_values)) if valid_values.size > 0 else float("nan"),
        max=float(np.max(valid_values)) if valid_values.size > 0 else float("nan"),
        std=float(np.std(valid_values)) if valid_values.size > 0 else float("nan"),
        valid_pixel_pct=float(computable.sum() / computable.size * 100),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile.update(count=1, dtype=np.float32, nodata=nodata_val)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(ndvi, 1)
        dst.update_tags(
            band_1="NDVI",
            ndvi_mean=f"{stats.mean:.4f}",
            ndvi_min=f"{stats.min:.4f}",
            ndvi_max=f"{stats.max:.4f}",
            ndvi_std=f"{stats.std:.4f}",
            ndvi_valid_pixel_pct=f"{stats.valid_pixel_pct:.2f}",
            source_file=str(input_path),
        )

    logger.info(
        "NDVI calculado | mean=%.3f min=%.3f max=%.3f válidos=%.1f%% | %s",
        stats.mean,
        stats.min,
        stats.max,
        stats.valid_pixel_pct,
        output_path,
    )
    return output_path, stats
