from datetime import date

from pydantic import BaseModel, Field


class DownloadRequest(BaseModel):
    date_from: date = Field(..., description="Inicio del rango de búsqueda (YYYY-MM-DD)")
    date_to: date = Field(..., description="Fin del rango de búsqueda (YYYY-MM-DD)")
    max_cloud_pct: float = Field(30.0, ge=0, le=100, description="Nubosidad máxima %")
    resolution: int = Field(10, ge=10, le=60, description="Resolución en metros")


class DownloadResponse(BaseModel):
    predio_id: str
    file_path: str
    date_from: date
    date_to: date
    width_px: int
    height_px: int
    resolution_m: int


class ComputeRequest(BaseModel):
    date_from: date = Field(..., description="Fecha inicio usada en la descarga")
    date_to: date = Field(..., description="Fecha fin usada en la descarga")


class NDVIStatsSchema(BaseModel):
    mean: float
    min: float
    max: float
    std: float
    valid_pixel_pct: float = Field(..., description="% de píxeles sin nodata")


class ComputeResponse(BaseModel):
    predio_id: str
    ndvi_path: str
    date_from: date
    date_to: date
    stats: NDVIStatsSchema


class NDVIMetaResponse(BaseModel):
    predio_id: str
    date_from: date
    date_to: date
    # [[sur, oeste], [norte, este]] — formato nativo de Leaflet imageOverlay
    bounds_leaflet: list[list[float]]
    stats: NDVIStatsSchema


class AnomalyRequest(BaseModel):
    date_from: date = Field(..., description="Inicio del mes a evaluar")
    date_to: date = Field(..., description="Fin del mes a evaluar")
    threshold: float = Field(2.0, ge=0.5, le=4.0, description="Umbral z-score para anomalía")


class AnomalyStatsSchema(BaseModel):
    z_mean: float | None
    z_std: float | None
    pct_stress: float | None = Field(None, description="% píxeles con z < −threshold")
    pct_normal: float | None = Field(None, description="% píxeles dentro de ±threshold")
    pct_above: float | None = Field(None, description="% píxeles con z > +threshold")
    baseline_months: int


class AnomalyResponse(BaseModel):
    predio_id: str
    date_from: date
    date_to: date
    threshold: float
    zscore_path: str
    stats: AnomalyStatsSchema


class AnomalyMetaResponse(BaseModel):
    predio_id: str
    date_from: date
    date_to: date
    threshold: float
    bounds_leaflet: list[list[float]]
    stats: AnomalyStatsSchema


class TimeseriesPoint(BaseModel):
    date_from: date
    date_to: date
    label: str  # "Ene 2026" — para el eje X del gráfico
    mean: float | None
    min: float | None
    max: float | None
    std: float | None
    valid_pixel_pct: float | None


class TimeseriesResponse(BaseModel):
    predio_id: str
    points: list[TimeseriesPoint]
    count: int
