import asyncio
import json
import logging
from datetime import date
from pathlib import Path

import rasterio
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from shapely.errors import ShapelyError
from shapely.geometry import shape
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.auth import get_user_predio
from backend.config import settings
from backend.schemas import (
    AnomalyMetaResponse,
    AnomalyRequest,
    AnomalyResponse,
    AnomalyStatsSchema,
    ComputeRequest,
    ComputeResponse,
    DownloadRequest,
    DownloadResponse,
    NDVIMetaResponse,
    NDVIStatsSchema,
    TimeseriesPoint,
    TimeseriesResponse,
)
from backend.services.anomaly import compute_anomaly
from backend.services.ndvi import compute_ndvi
from backend.services.render import ndvi_to_png, zscore_to_png
from backend.services.sentinel import download_sentinel2
from backend.services.timeseries import read_timeseries

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ndvi", tags=["ndvi"])
limiter = Limiter(key_func=get_remote_address)


def _detail(internal: str, status: int) -> str:
    """Oculta detalles internos en producción; los muestra en dev."""
    if settings.environment == "production":
        return "Recurso no encontrado" if status == 404 else "Error interno"
    return internal

DATA_DIR = Path("data")
PREDIOS_DIR = DATA_DIR / "predios"
RAW_DIR = DATA_DIR / "raw"
NDVI_DIR = DATA_DIR / "ndvi"
ANOMALY_DIR = DATA_DIR / "anomaly"

_MONTH_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _load_predio_bbox(predio_id: str) -> tuple[float, float, float, float]:
    """Devuelve (min_lon, min_lat, max_lon, max_lat) del primer feature del GeoJSON."""
    geojson_path = PREDIOS_DIR / f"{predio_id}.geojson"
    if not geojson_path.resolve().is_relative_to(PREDIOS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Predio ID inválido")
    if not geojson_path.exists():
        raise HTTPException(status_code=404, detail=f"Predio '{predio_id}' no encontrado")

    with geojson_path.open() as f:
        fc = json.load(f)

    try:
        geom_dict = fc["features"][0]["geometry"]
        geom = shape(geom_dict)
    except (KeyError, IndexError, ShapelyError) as exc:
        raise HTTPException(
            status_code=422, detail=f"GeoJSON inválido para '{predio_id}'"
        ) from exc

    min_lon, min_lat, max_lon, max_lat = geom.bounds
    return min_lon, min_lat, max_lon, max_lat


def _ndvi_path(predio_id: str, date_from: date, date_to: date) -> Path:
    path = NDVI_DIR / predio_id / f"{date_from}_{date_to}_NDVI.tif"
    if not path.resolve().is_relative_to(NDVI_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Predio ID inválido")
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"NDVI no encontrado para '{predio_id}' "
                f"({date_from} → {date_to}). Ejecuta /compute primero."
            ),
        )
    return path


@router.post("/predios/{predio_id}/download", response_model=DownloadResponse)
@limiter.limit("5/second")
async def download_predio(request: Request, predio_id: str = Depends(get_user_predio), body: DownloadRequest = ...) -> DownloadResponse:
    """Descarga bandas B04/B08 de Sentinel-2 para el predio indicado."""
    logger.info("download | predio=%s date_from=%s date_to=%s", predio_id, body.date_from, body.date_to)
    bbox = _load_predio_bbox(predio_id)
    output_path = RAW_DIR / predio_id / f"{body.date_from}_{body.date_to}_B04B08.tif"

    def _get_dims(p: Path) -> tuple[int, int]:
        with rasterio.open(p) as ds:
            return ds.width, ds.height

    if output_path.exists():
        width, height = await asyncio.to_thread(_get_dims, output_path)
        return DownloadResponse(
            predio_id=predio_id,
            date_from=body.date_from,
            date_to=body.date_to,
            width_px=width,
            height_px=height,
            resolution_m=body.resolution,
        )

    try:
        path = await asyncio.to_thread(
            download_sentinel2,
            bbox_coords=bbox,
            date_from=body.date_from,
            date_to=body.date_to,
            output_path=output_path,
            resolution=body.resolution,
            max_cloud_pct=body.max_cloud_pct,
        )
    except ValueError as exc:
        logger.exception("download ValueError | predio=%s", predio_id)
        raise HTTPException(status_code=404, detail=_detail(str(exc), 404)) from exc
    except RuntimeError as exc:
        logger.exception("download RuntimeError | predio=%s", predio_id)
        raise HTTPException(status_code=503, detail=_detail(str(exc), 503)) from exc

    width, height = await asyncio.to_thread(_get_dims, path)

    return DownloadResponse(
        predio_id=predio_id,
        date_from=body.date_from,
        date_to=body.date_to,
        width_px=width,
        height_px=height,
        resolution_m=body.resolution,
    )


@router.post("/predios/{predio_id}/compute", response_model=ComputeResponse)
@limiter.limit("5/second")
async def compute_predio_ndvi(request: Request, predio_id: str = Depends(get_user_predio), body: ComputeRequest = ...) -> ComputeResponse:
    """Calcula NDVI desde el GeoTIFF B04/B08 previamente descargado."""
    logger.info("compute | predio=%s date_from=%s date_to=%s", predio_id, body.date_from, body.date_to)
    input_path = RAW_DIR / predio_id / f"{body.date_from}_{body.date_to}_B04B08.tif"
    if not input_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No se encontró el archivo de bandas para '{predio_id}' "
                f"({body.date_from} → {body.date_to}). Ejecuta /download primero."
            ),
        )

    output_path = NDVI_DIR / predio_id / f"{body.date_from}_{body.date_to}_NDVI.tif"

    if output_path.exists():
        def _read_cached_stats(p: Path) -> NDVIStatsSchema:
            with rasterio.open(p) as ds:
                t = ds.tags()
            def _f(k: str) -> float:
                try:
                    return float(t[k])
                except (KeyError, ValueError):
                    return float("nan")
            return NDVIStatsSchema(
                mean=_f("ndvi_mean"), min=_f("ndvi_min"), max=_f("ndvi_max"),
                std=_f("ndvi_std"), valid_pixel_pct=_f("ndvi_valid_pixel_pct"),
            )
        cached = await asyncio.to_thread(_read_cached_stats, output_path)
        return ComputeResponse(
            predio_id=predio_id,
            date_from=body.date_from,
            date_to=body.date_to,
            stats=cached,
        )

    try:
        ndvi_path, stats = await asyncio.to_thread(compute_ndvi, input_path, output_path)
    except (ValueError, FileNotFoundError) as exc:
        logger.exception("compute error | predio=%s", predio_id)
        raise HTTPException(status_code=422, detail=_detail(str(exc), 422)) from exc

    return ComputeResponse(
        predio_id=predio_id,
        date_from=body.date_from,
        date_to=body.date_to,
        stats=NDVIStatsSchema(
            mean=stats.mean,
            min=stats.min,
            max=stats.max,
            std=stats.std,
            valid_pixel_pct=stats.valid_pixel_pct,
        ),
    )


@router.get("/predios/{predio_id}/image")
@limiter.limit("30/minute")
def get_ndvi_image(
    request: Request,
    predio_id: str = Depends(get_user_predio),
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> Response:
    """Devuelve el NDVI como PNG RGBA coloreado (RdYlGn) para imageOverlay en Leaflet."""
    logger.info("image | predio=%s date_from=%s date_to=%s", predio_id, date_from, date_to)
    ndvi_tif = _ndvi_path(predio_id, date_from, date_to)
    try:
        png_bytes, _ = ndvi_to_png(ndvi_tif)
    except FileNotFoundError as exc:
        logger.exception("image FileNotFoundError | predio=%s", predio_id)
        raise HTTPException(status_code=404, detail=_detail(str(exc), 404)) from exc

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/predios/{predio_id}/meta", response_model=NDVIMetaResponse)
def get_ndvi_meta(
    predio_id: str = Depends(get_user_predio),
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> NDVIMetaResponse:
    """Devuelve bounds (formato Leaflet) y estadísticas del NDVI calculado."""
    logger.info("meta | predio=%s date_from=%s date_to=%s", predio_id, date_from, date_to)
    ndvi_tif = _ndvi_path(predio_id, date_from, date_to)

    with rasterio.open(ndvi_tif) as ds:
        b = ds.bounds
        tags = ds.tags()

    def _tag_float(key: str) -> float:
        try:
            return float(tags[key])
        except (KeyError, ValueError):
            return float("nan")

    return NDVIMetaResponse(
        predio_id=predio_id,
        date_from=date_from,
        date_to=date_to,
        bounds_leaflet=[[b.bottom, b.left], [b.top, b.right]],
        stats=NDVIStatsSchema(
            mean=_tag_float("ndvi_mean"),
            min=_tag_float("ndvi_min"),
            max=_tag_float("ndvi_max"),
            std=_tag_float("ndvi_std"),
            valid_pixel_pct=_tag_float("ndvi_valid_pixel_pct"),
        ),
    )


@router.get("/predios/{predio_id}/timeseries", response_model=TimeseriesResponse)
def get_timeseries(predio_id: str = Depends(get_user_predio)) -> TimeseriesResponse:
    """Devuelve la serie temporal NDVI de todos los meses calculados para el predio."""
    logger.info("timeseries | predio=%s", predio_id)
    predio_ndvi_dir = NDVI_DIR / predio_id
    raw_points = read_timeseries(predio_ndvi_dir)

    def _or_none(v: float) -> float | None:
        return None if (v != v) else v  # NaN check

    schema_points = [
        TimeseriesPoint(
            date_from=p.date_from,
            date_to=p.date_to,
            label=f"{_MONTH_ES[p.date_from.month]} {p.date_from.year}",
            mean=_or_none(p.mean),
            min=_or_none(p.min),
            max=_or_none(p.max),
            std=_or_none(p.std),
            valid_pixel_pct=_or_none(p.valid_pixel_pct),
        )
        for p in raw_points
    ]

    return TimeseriesResponse(
        predio_id=predio_id,
        points=schema_points,
        count=len(schema_points),
    )


# ── Anomalías ────────────────────────────────────────────────────────────────

def _zscore_path(predio_id: str, date_from: date, date_to: date) -> Path:
    path = ANOMALY_DIR / predio_id / f"{date_from}_{date_to}_zscore.tif"
    if not path.resolve().is_relative_to(ANOMALY_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Predio ID inválido")
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Z-score no encontrado para '{predio_id}' "
                f"({date_from} → {date_to}). Ejecuta /anomaly primero."
            ),
        )
    return path


@router.post("/predios/{predio_id}/anomaly", response_model=AnomalyResponse)
@limiter.limit("5/second")
def detect_anomaly(request: Request, predio_id: str = Depends(get_user_predio), body: AnomalyRequest = ...) -> AnomalyResponse:
    """Calcula el z-score NDVI del mes indicado frente al resto de la serie temporal."""
    logger.info("anomaly | predio=%s date_from=%s date_to=%s", predio_id, body.date_from, body.date_to)
    output_path = ANOMALY_DIR / predio_id / f"{body.date_from}_{body.date_to}_zscore.tif"

    try:
        zscore_path, stats = compute_anomaly(
            predio_ndvi_dir=NDVI_DIR / predio_id,
            target_date_from=body.date_from,
            target_date_to=body.date_to,
            output_path=output_path,
            threshold=body.threshold,
        )
    except FileNotFoundError as exc:
        logger.exception("anomaly FileNotFoundError | predio=%s", predio_id)
        raise HTTPException(status_code=404, detail=_detail(str(exc), 404)) from exc
    except ValueError as exc:
        logger.exception("anomaly ValueError | predio=%s", predio_id)
        raise HTTPException(status_code=422, detail=_detail(str(exc), 422)) from exc

    def _or_none(v: float) -> float | None:
        return None if (v != v) else v

    return AnomalyResponse(
        predio_id=predio_id,
        date_from=body.date_from,
        date_to=body.date_to,
        threshold=body.threshold,
        stats=AnomalyStatsSchema(
            z_mean=_or_none(stats.z_mean),
            z_std=_or_none(stats.z_std),
            pct_stress=_or_none(stats.pct_stress),
            pct_normal=_or_none(stats.pct_normal),
            pct_above=_or_none(stats.pct_above),
            baseline_months=stats.baseline_months,
        ),
    )


@router.get("/predios/{predio_id}/anomaly/image")
@limiter.limit("30/minute")
def get_anomaly_image(
    request: Request,
    predio_id: str = Depends(get_user_predio),
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> Response:
    """Devuelve el mapa de z-score como PNG RGBA (RdBu) para imageOverlay en Leaflet."""
    logger.info("anomaly/image | predio=%s date_from=%s date_to=%s", predio_id, date_from, date_to)
    zpath = _zscore_path(predio_id, date_from, date_to)
    try:
        png_bytes, _ = zscore_to_png(zpath)
    except FileNotFoundError as exc:
        logger.exception("anomaly/image FileNotFoundError | predio=%s", predio_id)
        raise HTTPException(status_code=404, detail=_detail(str(exc), 404)) from exc
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/predios/{predio_id}/anomaly/meta", response_model=AnomalyMetaResponse)
def get_anomaly_meta(
    predio_id: str = Depends(get_user_predio),
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> AnomalyMetaResponse:
    """Devuelve bounds y estadísticas del z-score calculado."""
    logger.info("anomaly/meta | predio=%s date_from=%s date_to=%s", predio_id, date_from, date_to)
    zpath = _zscore_path(predio_id, date_from, date_to)

    with rasterio.open(zpath) as ds:
        b = ds.bounds
        tags = ds.tags()

    def _tf(key: str) -> float | None:
        try:
            v = float(tags[key])
            return None if (v != v) else v
        except (KeyError, ValueError):
            return None

    return AnomalyMetaResponse(
        predio_id=predio_id,
        date_from=date_from,
        date_to=date_to,
        threshold=float(tags.get("threshold", 2.0)),
        bounds_leaflet=[[b.bottom, b.left], [b.top, b.right]],
        stats=AnomalyStatsSchema(
            z_mean=_tf("z_mean"),
            z_std=_tf("z_std"),
            pct_stress=_tf("pct_stress"),
            pct_normal=_tf("pct_normal"),
            pct_above=_tf("pct_above"),
            baseline_months=int(tags.get("baseline_months", 0)),
        ),
    )
