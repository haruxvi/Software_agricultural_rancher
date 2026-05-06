"""
Genera GeoTIFFs NDVI sintéticos para 12 meses — permite ver la serie temporal
sin credenciales de Sentinel Hub.

Fenología realista de vid en Colchagua (Hemisferio Sur):
  Ene–Feb: canopia plena (NDVI alto)
  Mar–Abr: cosecha y senescencia (declive)
  May–Jul: dormancia (NDVI bajo)
  Ago–Sep: brotación (ascenso)
  Oct–Dic: crecimiento activo (sube hasta diciembre)

Uso:
    python scripts/generate_test_data.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

sys.path.insert(0, str(Path(__file__).parent.parent))

BBOX = (-71.3800, -34.6520, -71.3650, -34.6400)
NODATA = -9999.0
WIDTH, HEIGHT = 130, 112  # ~10 m resolución para ~45 ha

# NDVI promedio mensual para viña en Colchagua (values 1–12)
_NDVI_MONTHLY_MEAN = {
    1: 0.68, 2: 0.63, 3: 0.53, 4: 0.38,
    5: 0.22, 6: 0.13, 7: 0.11, 8: 0.14,
    9: 0.22, 10: 0.33, 11: 0.47, 12: 0.62,
}


def _generate_ndvi_array(mean: float, rng: np.random.Generator) -> np.ndarray:
    """Imagen NDVI sintética con variación espacial realista."""
    std = 0.06
    noise = rng.normal(0, std, (HEIGHT, WIDTH)).astype(np.float32)
    # Gradiente suave N-S (exposición solar)
    gradient = np.linspace(-0.04, 0.04, HEIGHT, dtype=np.float32)[:, np.newaxis]
    ndvi = np.clip(mean + noise + gradient, -0.1, 0.95).astype(np.float32)
    # 5 % de píxeles como nodata (nubes residuales)
    cloud_mask = rng.random((HEIGHT, WIDTH)) < 0.05
    ndvi[cloud_mask] = NODATA
    return ndvi


def _first_last_of_month(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def generate(output_dir: Path, months: int = 12) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    transform = from_bounds(*BBOX, WIDTH, HEIGHT)

    today = date.today()
    # Retroceder `months` meses desde el mes anterior al actual
    generated = []
    year, month = today.year, today.month - 1
    if month == 0:
        month, year = 12, year - 1

    for _ in range(months):
        date_from, date_to = _first_last_of_month(year, month)
        mean = _NDVI_MONTHLY_MEAN[month]
        ndvi = _generate_ndvi_array(mean, rng)

        valid = ndvi[ndvi != NODATA]
        stats = {
            "mean": float(np.mean(valid)),
            "min":  float(np.min(valid)),
            "max":  float(np.max(valid)),
            "std":  float(np.std(valid)),
            "valid_pixel_pct": float((ndvi != NODATA).sum() / ndvi.size * 100),
        }

        out_path = output_dir / f"{date_from}_{date_to}_NDVI.tif"
        with rasterio.open(
            out_path, "w", driver="GTiff",
            height=HEIGHT, width=WIDTH, count=1, dtype=np.float32,
            crs=CRS.from_epsg(4326), transform=transform, nodata=NODATA,
        ) as dst:
            dst.write(ndvi, 1)
            dst.update_tags(
                band_1="NDVI",
                ndvi_mean=f"{stats['mean']:.4f}",
                ndvi_min=f"{stats['min']:.4f}",
                ndvi_max=f"{stats['max']:.4f}",
                ndvi_std=f"{stats['std']:.4f}",
                ndvi_valid_pixel_pct=f"{stats['valid_pixel_pct']:.2f}",
                source_file="synthetic",
            )

        generated.append((date_from, stats["mean"]))
        print(f"  {date_from} -> {date_to}  NDVI media={stats['mean']:.3f}  [{out_path.name}]")

        month -= 1
        if month == 0:
            month, year = 12, year - 1

    print(f"\n{len(generated)} GeoTIFFs generados en {output_dir}")


if __name__ == "__main__":
    out = Path("data/ndvi/predio_prueba")
    print(f"Generando datos sintéticos en {out} ...\n")
    generate(out, months=12)
