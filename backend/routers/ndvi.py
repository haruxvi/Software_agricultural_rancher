import json
import logging
from datetime import date
from pathlib import Path
from typing import Annotated

import rasterio
from fastapi import APIRouter, Depends, HTTPException, Path as FPath, Query
from fastapi.responses import Response

from backend.auth import get_current_user
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
router = APIRouter(prefix="/ndvi", tags=["ndvi"], dependencies=[Depends(get_current_user)])

# Solo alfanumérico + guiones — previene path traversal
PredioId = Annotated[str, FPath(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]

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
    if not geojson_path.exists():
        raise HTTPException(status_code=404, detail=f"Predio '{predio_id}' no encontrado")

    with geojson_path.open() as f:
        fc = json.load(f)

    coords = fc["features"][0]["geometry"]["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return min(lons), min(lats), max(lons), max(lats)


def _ndvi_path(predio_id: str, date_from: date, date_to: date) -> Path:
    path = NDVI_DIR / predio_id / f"{date_from}_{date_to}_NDVI.tif"
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
def download_predio(predio_id: PredioId, body: DownloadRequest) -> DownloadResponse:
    """Descarga bandas B04/B08 de Sentinel-2 para el predio indicado."""
    if body.date_from > body.date_to:
        raise HTTPException(status_code=422, detail="date_from debe ser anterior a date_to")

    bbox = _load_predio_bbox(predio_id)
    output_path = RAW_DIR / predio_id / f"{body.date_from}_{body.date_to}_B04B08.tif"

    try:
        path = download_sentinel2(
            bbox_coords=bbox,
            date_from=body.date_from,
            date_to=body.date_to,
            output_path=output_path,
            resolution=body.resolution,
            max_cloud_pct=body.max_cloud_pct,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    with rasterio.open(path) as ds:
        width, height = ds.width, ds.height

    return DownloadResponse(
        predio_id=predio_id,
        date_from=body.date_from,
        date_to=body.date_to,
        width_px=width,
        height_px=height,
        resolution_m=body.resolution,
    )


@router.post("/predios/{predio_id}/compute", response_model=ComputeResponse)
def compute_predio_ndvi(predio_id: PredioId, body: ComputeRequest) -> ComputeResponse:
    """Calcula NDVI desde el GeoTIFF B04/B08 previamente descargado."""
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

    try:
        ndvi_path, stats = compute_ndvi(input_path, output_path)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
def get_ndvi_image(
    predio_id: PredioId,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> Response:
    """Devuelve el NDVI como PNG RGBA coloreado (RdYlGn) para imageOverlay en Leaflet."""
    ndvi_tif = _ndvi_path(predio_id, date_from, date_to)
    try:
        png_bytes, _ = ndvi_to_png(ndvi_tif)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(content=png_bytes, media_type="image/png")


@router.get("/predios/{predio_id}/meta", response_model=NDVIMetaResponse)
def get_ndvi_meta(
    predio_id: PredioId,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> NDVIMetaResponse:
    """Devuelve bounds (formato Leaflet) y estadísticas del NDVI calculado."""
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
def get_timeseries(predio_id: PredioId) -> TimeseriesResponse:
    """Devuelve la serie temporal NDVI de todos los meses calculados para el predio."""
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
def detect_anomaly(predio_id: PredioId, body: AnomalyRequest) -> AnomalyResponse:
    """Calcula el z-score NDVI del mes indicado frente al resto de la serie temporal."""
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
def get_anomaly_image(
    predio_id: PredioId,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> Response:
    """Devuelve el mapa de z-score como PNG RGBA (RdBu) para imageOverlay en Leaflet."""
    zpath = _zscore_path(predio_id, date_from, date_to)
    try:
        png_bytes, _ = zscore_to_png(zpath)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=png_bytes, media_type="image/png")


@router.get("/predios/{predio_id}/anomaly/meta", response_model=AnomalyMetaResponse)
def get_anomaly_meta(
    predio_id: PredioId,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> AnomalyMetaResponse:
    """Devuelve bounds y estadísticas del z-score calculado."""
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
