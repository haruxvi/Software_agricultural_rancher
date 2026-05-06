"""Lectura de serie temporal NDVI desde los GeoTIFFs ya calculados en disco."""

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import rasterio

logger = logging.getLogger(__name__)

_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_NDVI\.tif$")


@dataclass(frozen=True)
class TimeseriesPoint:
    date_from: date
    date_to: date
    mean: float
    min: float
    max: float
    std: float
    valid_pixel_pct: float


def read_timeseries(predio_ndvi_dir: Path) -> list[TimeseriesPoint]:
    """
    Escanea todos los GeoTIFFs NDVI de un predio y devuelve la serie temporal.

    Lee las estadísticas desde los tags del GeoTIFF (escritos por compute_ndvi),
    sin releer los píxeles. Ordena por date_from ascendente.

    Args:
        predio_ndvi_dir: directorio data/ndvi/{predio_id}/

    Returns:
        Lista de TimeseriesPoint ordenada por fecha, vacía si no hay archivos.
    """
    if not predio_ndvi_dir.exists():
        logger.info("Directorio NDVI no existe: %s", predio_ndvi_dir)
        return []

    points: list[TimeseriesPoint] = []

    for tif in predio_ndvi_dir.glob("*.tif"):
        m = _FNAME_RE.match(tif.name)
        if not m:
            logger.debug("Archivo ignorado (nombre inesperado): %s", tif.name)
            continue

        date_from = date.fromisoformat(m.group(1))
        date_to   = date.fromisoformat(m.group(2))

        try:
            with rasterio.open(tif) as ds:
                tags = ds.tags()
        except Exception:
            logger.warning("No se pudo leer %s, se omite.", tif)
            continue

        def _f(key: str) -> float:
            try:
                return float(tags[key])
            except (KeyError, ValueError):
                return float("nan")

        points.append(
            TimeseriesPoint(
                date_from=date_from,
                date_to=date_to,
                mean=_f("ndvi_mean"),
                min=_f("ndvi_min"),
                max=_f("ndvi_max"),
                std=_f("ndvi_std"),
                valid_pixel_pct=_f("ndvi_valid_pixel_pct"),
            )
        )

    points.sort(key=lambda p: p.date_from)
    logger.info("Serie temporal: %d puntos para %s", len(points), predio_ndvi_dir.name)
    return points
