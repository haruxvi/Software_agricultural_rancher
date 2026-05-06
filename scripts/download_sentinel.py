"""
Script standalone para descargar una imagen Sentinel-2 del predio de prueba.

Uso:
    python scripts/download_sentinel.py
    python scripts/download_sentinel.py --date-from 2026-02-01 --date-to 2026-03-01
"""

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Agrega la raíz del proyecto al path para poder importar backend.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.sentinel import download_sentinel2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Predio de prueba: Viña Colchagua (del GeoJSON sintético)
BBOX_PRUEBA = (-71.3800, -34.6520, -71.3650, -34.6400)  # (min_lon, min_lat, max_lon, max_lat)


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga Sentinel-2 para predio de prueba")
    parser.add_argument(
        "--date-from",
        default=(date.today() - timedelta(days=60)).isoformat(),
        help="Fecha inicio (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--date-to",
        default=(date.today() - timedelta(days=1)).isoformat(),
        help="Fecha fin (YYYY-MM-DD)",
    )
    parser.add_argument("--cloud", type=float, default=30.0, help="Nubosidad máxima %%")
    parser.add_argument("--resolution", type=int, default=10, help="Resolución en metros")
    args = parser.parse_args()

    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to)
    output = Path("data/raw/predio_prueba") / f"{date_from}_{date_to}_B04B08.tif"

    print(f"Descargando S2 para predio de prueba...")
    print(f"  BBox    : {BBOX_PRUEBA}")
    print(f"  Fechas  : {date_from} → {date_to}")
    print(f"  Nube ≤  : {args.cloud}%")
    print(f"  Output  : {output}")

    try:
        path = download_sentinel2(
            bbox_coords=BBOX_PRUEBA,
            date_from=date_from,
            date_to=date_to,
            output_path=output,
            resolution=args.resolution,
            max_cloud_pct=args.cloud,
        )
        print(f"\nDescarga exitosa: {path}")

        import rasterio
        with rasterio.open(path) as ds:
            print(f"  Tamaño  : {ds.width} x {ds.height} px")
            print(f"  Bandas  : {ds.count} (B04=1, B08=2)")
            print(f"  CRS     : {ds.crs}")
            print(f"  Nodata  : {ds.nodata}")
            b04_min, b04_max = ds.read(1).min(), ds.read(1).max()
            b08_min, b08_max = ds.read(2).min(), ds.read(2).max()
            print(f"  B04 rango: [{b04_min:.4f}, {b04_max:.4f}]")
            print(f"  B08 rango: [{b08_min:.4f}, {b08_max:.4f}]")

    except (ValueError, RuntimeError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
