"""Detección de anomalías NDVI con z-score pixel a pixel."""

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import rasterio

from backend.utils.log_safe import sanitize_for_log

logger = logging.getLogger(__name__)

MIN_BASELINE_MONTHS = 3
NODATA = -9999.0
_FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_NDVI\.tif$")


@dataclass(frozen=True)
class AnomalyStats:
    z_mean: float          # z-score promedio de píxeles válidos
    z_std: float           # desviación estándar de z-scores
    pct_stress: float      # % píxeles con z < −threshold (estrés)
    pct_normal: float      # % píxeles dentro de ±threshold
    pct_above: float       # % píxeles con z > +threshold (sobre lo normal)
    baseline_months: int   # meses usados como referencia


def compute_anomaly(
    predio_ndvi_dir: Path,
    target_date_from: date,
    target_date_to: date,
    output_path: Path,
    threshold: float = 2.0,
) -> tuple[Path, AnomalyStats]:
    """
    Calcula el z-score NDVI para un mes objetivo respecto al resto de meses disponibles.

    Algoritmo:
        1. Separa el mes objetivo del resto (baseline).
        2. Apila el baseline en (N, H, W) con numpy masked arrays.
        3. Calcula media y std pixel a pixel sobre el baseline.
        4. z = (NDVI_objetivo - media) / std  (std=0 → nodata).
        5. Clasifica píxeles en estrés / normal / sobre lo normal.

    Args:
        predio_ndvi_dir: directorio data/ndvi/{predio_id}/
        target_date_from / target_date_to: mes a evaluar.
        output_path: ruta del GeoTIFF z-score resultante.
        threshold: umbral de z-score para clasificar anomalía (default 2.0).

    Returns:
        (output_path, AnomalyStats)

    Raises:
        FileNotFoundError: si el GeoTIFF del mes objetivo no existe.
        ValueError: si hay menos de MIN_BASELINE_MONTHS meses de baseline.
    """
    target_name = f"{target_date_from}_{target_date_to}_NDVI.tif"
    target_path = predio_ndvi_dir / target_name
    if not target_path.exists():
        raise FileNotFoundError(
            f"GeoTIFF objetivo no encontrado: {target_path}. "
            "Ejecuta /compute primero para ese mes."
        )

    # Recolectar baseline (todos menos el objetivo)
    baseline_paths: list[Path] = []
    for tif in predio_ndvi_dir.glob("*.tif"):
        m = _FNAME_RE.match(tif.name)
        if not m or tif.name == target_name:
            continue
        baseline_paths.append(tif)

    if len(baseline_paths) < MIN_BASELINE_MONTHS:
        raise ValueError(
            f"Se necesitan al menos {MIN_BASELINE_MONTHS} meses de baseline, "
            f"solo hay {len(baseline_paths)}. Calcula más meses con /compute."
        )

    # Leer target
    with rasterio.open(target_path) as src:
        target = src.read(1).astype(np.float32)
        profile = src.profile.copy()

    h, w = target.shape

    # Apilar baseline como masked array (N, H, W)
    layers: list[np.ndarray] = []
    for p in baseline_paths:
        with rasterio.open(p) as src:
            arr = src.read(1).astype(np.float32)
        layers.append(arr)

    stack = np.stack(layers)                        # (N, H, W)
    masked_stack = np.ma.masked_equal(stack, NODATA)

    # Media y std pixel a pixel sobre baseline (ddof=1 → muestra)
    with np.errstate(invalid="ignore"):
        pixel_mean = masked_stack.mean(axis=0).filled(NODATA)
        pixel_std  = masked_stack.std(axis=0, ddof=1).filled(NODATA)

    # Z-score: solo donde target, mean y std son válidos y std > 0
    valid = (
        (target != NODATA)
        & (pixel_mean != NODATA)
        & (pixel_std != NODATA)
        & (pixel_std > 1e-6)
    )

    zscore = np.full((h, w), fill_value=NODATA, dtype=np.float32)
    zscore[valid] = (target[valid] - pixel_mean[valid]) / pixel_std[valid]

    # Estadísticas sobre píxeles válidos
    valid_z = zscore[valid]
    n_valid = valid_z.size
    if n_valid > 0:
        stats = AnomalyStats(
            z_mean=float(np.mean(valid_z)),
            z_std=float(np.std(valid_z)),
            pct_stress=float((valid_z < -threshold).sum() / n_valid * 100),
            pct_normal=float(
                ((valid_z >= -threshold) & (valid_z <= threshold)).sum() / n_valid * 100
            ),
            pct_above=float((valid_z > threshold).sum() / n_valid * 100),
            baseline_months=len(baseline_paths),
        )
    else:
        stats = AnomalyStats(
            z_mean=float("nan"), z_std=float("nan"),
            pct_stress=float("nan"), pct_normal=float("nan"), pct_above=float("nan"),
            baseline_months=len(baseline_paths),
        )

    # Guardar GeoTIFF z-score
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile.update(count=1, dtype=np.float32, nodata=NODATA)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(zscore, 1)
        dst.update_tags(
            band_1="z_score_ndvi",
            threshold=str(threshold),
            baseline_months=str(stats.baseline_months),
            pct_stress=f"{stats.pct_stress:.2f}",
            pct_normal=f"{stats.pct_normal:.2f}",
            pct_above=f"{stats.pct_above:.2f}",
            z_mean=f"{stats.z_mean:.4f}",
            z_std=f"{stats.z_std:.4f}",
        )

    logger.info(
        "Z-score calculado | baseline=%d meses | estrés=%.1f%% normal=%.1f%% sobre=%.1f%% | %s",
        stats.baseline_months, stats.pct_stress, stats.pct_normal, stats.pct_above, sanitize_for_log(output_path),
    )
    return output_path, stats
