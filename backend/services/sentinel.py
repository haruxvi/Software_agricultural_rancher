"""Descarga de bandas Sentinel-2 vía Copernicus Data Space (sentinelhub-py)."""

import logging
import time
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

# Import lazy: sentinelhub es opcional en entornos sin credenciales
try:
    from sentinelhub import CRS as SentinelCRS  # type: ignore[import-untyped]
    from sentinelhub import (  # type: ignore[import-untyped]
        BBox,
        DataCollection,
        MimeType,
        SentinelHubRequest,
        SHConfig,
        bbox_to_dimensions,
    )
    _SH_AVAILABLE = True
except ModuleNotFoundError:
    _SH_AVAILABLE = False

from backend.config import settings

logger = logging.getLogger(__name__)

# Resolución espacial en metros (10 m = resolución nativa B04/B08)
DEFAULT_RESOLUTION = 10

# Evalscript: devuelve B04 (rojo) y B08 (NIR) como reflectancia [0..1]
EVALSCRIPT_B04_B08 = """
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL"] }],
    output: { bands: 2, sampleType: "FLOAT32" }
  };
}
function evaluatePixel(sample) {
  // SCL band 3=shadow, 8=cloud_medium, 9=cloud_high, 10=cirrus → enmascarar
  if ([3, 8, 9, 10].includes(sample.SCL)) {
    return [-9999, -9999];
  }
  return [sample.B04 / 10000.0, sample.B08 / 10000.0];
}
"""


def _build_config() -> SHConfig:
    config = SHConfig()
    config.sh_client_id = settings.sh_client_id
    config.sh_client_secret = settings.sh_client_secret
    # Endpoints de Copernicus Data Space Ecosystem (CDSE)
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"
    config.sh_token_url = (
        "https://identity.dataspace.copernicus.eu"
        "/auth/realms/CDSE/protocol/openid-connect/token"
    )
    return config


def _cdse_collection() -> DataCollection:
    """Registra S2-L2A apuntando a CDSE (solo una vez por proceso)."""
    name = "SENTINEL2_L2A_CDSE"
    try:
        return DataCollection[name]
    except KeyError:
        return DataCollection.SENTINEL2_L2A.define_from(
            name,
            service_url="https://sh.dataspace.copernicus.eu",
        )


def download_sentinel2(
    bbox_coords: tuple[float, float, float, float],
    date_from: date,
    date_to: date,
    output_path: Path,
    resolution: int = DEFAULT_RESOLUTION,
    max_cloud_pct: float = 30.0,
) -> Path:
    """
    Descarga bandas B04 y B08 de Sentinel-2 L2A para un bbox y rango de fechas.

    Args:
        bbox_coords: (min_lon, min_lat, max_lon, max_lat) en WGS84.
        date_from / date_to: rango de búsqueda (inclusive).
        output_path: ruta completa del GeoTIFF a escribir.
        resolution: resolución en metros (default 10 m).
        max_cloud_pct: porcentaje máximo de nubosidad permitido.

    Returns:
        Path del archivo GeoTIFF escrito.

    Raises:
        ValueError: si no hay escenas disponibles en el rango.
        RuntimeError: si la descarga falla.
    """
    if not _SH_AVAILABLE:
        raise RuntimeError(
            "sentinelhub no está instalado. "
            "Ejecuta: pip install sentinelhub"
        )
    if not settings.sh_client_id or not settings.sh_client_secret:
        raise RuntimeError(
            "Credenciales de Sentinel Hub no configuradas. "
            "Verifica SH_CLIENT_ID y SH_CLIENT_SECRET en .env"
        )

    config = _build_config()
    collection = _cdse_collection()

    sh_bbox = BBox(bbox=bbox_coords, crs=SentinelCRS.WGS84)
    size = bbox_to_dimensions(sh_bbox, resolution=resolution)
    logger.info(
        "Descargando S2 | bbox=%s | fechas=%s→%s | tamaño=%s px | nube≤%.0f%%",
        bbox_coords,
        date_from,
        date_to,
        size,
        max_cloud_pct,
    )

    request = SentinelHubRequest(
        evalscript=EVALSCRIPT_B04_B08,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=collection,
                time_interval=(date_from.isoformat(), date_to.isoformat()),
                mosaicking_order="leastCC",  # prioriza menor cobertura de nubes
                other_args={"dataFilter": {"maxCloudCoverage": max_cloud_pct}},
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=sh_bbox,
        size=size,
        config=config,
    )

    _MAX_RETRIES = 3
    _TIMEOUT_S = 60
    data = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            data = request.get_data(decode_data=True, save_data=False)
            break
        except Exception as exc:
            is_timeout = "timeout" in str(exc).lower() or "timed out" in str(exc).lower()
            if attempt == _MAX_RETRIES:
                if is_timeout:
                    raise RuntimeError(
                        f"Sentinel Hub no respondió en {_TIMEOUT_S}s tras {_MAX_RETRIES} intentos"
                    ) from exc
                raise RuntimeError(f"Error descargando desde Sentinel Hub: {exc}") from exc
            wait = 2 ** attempt
            logger.warning("Intento %d/%d fallido (%s). Reintentando en %ds…", attempt, _MAX_RETRIES, exc, wait)
            time.sleep(wait)

    if not data or data[0] is None:
        raise ValueError(
            f"Sin escenas disponibles para bbox={bbox_coords} "
            f"entre {date_from} y {date_to} con nube≤{max_cloud_pct}%"
        )

    # data[0] tiene shape (height, width, 2): banda 0 = B04, banda 1 = B08
    image: np.ndarray = data[0].astype(np.float32)
    height, width, _ = image.shape

    output_path.parent.mkdir(parents=True, exist_ok=True)

    min_lon, min_lat, max_lon, max_lat = bbox_coords
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, width, height)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=2,
        dtype=np.float32,
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(image[:, :, 0], 1)  # B04 (rojo)
        dst.write(image[:, :, 1], 2)  # B08 (NIR)
        dst.update_tags(
            band_1="B04_red",
            band_2="B08_nir",
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            source="Sentinel-2 L2A / CDSE",
        )

    logger.info("GeoTIFF guardado en %s (%dx%d px)", output_path, width, height)
    return output_path
