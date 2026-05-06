"""Generación de reporte PDF con fpdf2 + matplotlib."""

import io
import json
import logging
from datetime import date
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")  # backend sin pantalla — debe ir antes de pyplot
import matplotlib.pyplot as plt
from fpdf import FPDF
from PIL import Image

from backend.services.render import ndvi_to_png, zscore_to_png
from backend.services.timeseries import read_timeseries

logger = logging.getLogger(__name__)

_MONTH_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# Paleta (R, G, B)
_GREEN  = (22, 163, 74)
_WHITE  = (255, 255, 255)
_DARK   = (17, 24, 39)
_GRAY   = (107, 114, 128)
_LGRAY  = (249, 250, 251)
_BORDER = (209, 213, 219)
_RED    = (220, 38, 38)
_BLUE   = (37, 99, 235)

A4_W   = 210
MARGIN = 15
COL_W  = (A4_W - 2 * MARGIN - 6) / 2  # dos columnas con 6 mm de hueco


# ── Helpers ────────────────────────────────────────────────────────────────────

def _png_to_buf(png_bytes: bytes) -> tuple[io.BytesIO, int, int]:
    """Devuelve (BytesIO, width_px, height_px) de un PNG."""
    img = Image.open(io.BytesIO(png_bytes))
    buf = io.BytesIO(png_bytes)
    return buf, img.width, img.height


def _scale_image(w_px: int, h_px: int, max_w_mm: float, max_h_mm: float) -> tuple[float, float]:
    """Calcula dimensiones (mm) manteniendo aspect ratio."""
    ratio = w_px / h_px
    w_mm = min(max_w_mm, max_h_mm * ratio)
    h_mm = w_mm / ratio
    if h_mm > max_h_mm:
        h_mm = max_h_mm
        w_mm = h_mm * ratio
    return w_mm, h_mm


def _timeseries_chart(points: list) -> io.BytesIO:
    """Genera gráfico de serie temporal como PNG en memoria."""
    labels = [p.date_from.strftime("%b %y") for p in points]
    means  = [p.mean  if p.mean  is not None else np.nan for p in points]
    maxv   = [p.max   if p.max   is not None else np.nan for p in points]
    minv   = [p.min   if p.min   is not None else np.nan for p in points]
    xs     = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(7.5, 2.4), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#f9fafb")

    ax.fill_between(xs, minv, maxv, color="#bbf7d0", alpha=0.6, label="Rango mín–máx")
    ax.plot(xs, means, color="#16a34a", linewidth=2, marker="o",
            markersize=4, markerfacecolor="#16a34a", markeredgecolor="white",
            markeredgewidth=1, label="NDVI Promedio", zorder=3)

    # Líneas de referencia
    ax.axhline(0.6, color="#15803d", linewidth=0.7, linestyle="--", alpha=0.5)
    ax.axhline(0.3, color="#ca8a04", linewidth=0.7, linestyle="--", alpha=0.5)
    ax.text(len(xs) - 0.5, 0.61, "0.6", fontsize=6, color="#15803d", va="bottom")
    ax.text(len(xs) - 0.5, 0.31, "0.3", fontsize=6, color="#ca8a04", va="bottom")

    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=7, rotation=45, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("NDVI", fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.grid(axis="y", color="#e5e7eb", linewidth=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7, loc="upper left", framealpha=0.8)

    plt.tight_layout(pad=0.4)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


# ── PDF class ──────────────────────────────────────────────────────────────────

class _PDF(FPDF):
    def __init__(self, predio_nombre: str, periodo: str) -> None:
        super().__init__(format="A4")
        self._predio = predio_nombre
        self._periodo = periodo
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        self.set_fill_color(*_GREEN)
        self.rect(0, 0, A4_W, 16, style="F")
        self.set_y(4)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*_WHITE)
        self.cell(0, 7, f"AgroVista  |  Reporte NDVI  -  {self._predio}", align="L")
        self.set_font("Helvetica", "", 8)
        self.set_y(4)
        self.cell(0, 7, self._periodo, align="R")
        self.set_text_color(*_DARK)
        self.ln(18)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_GRAY)
        today = date.today().isoformat()
        self.cell(0, 5,
                  f"Generado el {today}  |  AgroVista MVP  |  Datos satelitales: Sentinel-2 L2A / CDSE",
                  align="C")

    # ── Componentes ────────────────────────────────────────────────────────────

    def section_title(self, title: str) -> None:
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*_GREEN)
        self.cell(0, 5, title.upper(), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*_GREEN)
        self.set_line_width(0.5)
        self.line(MARGIN, self.get_y(), A4_W - MARGIN, self.get_y())
        self.set_line_width(0.2)
        self.set_draw_color(*_BORDER)
        self.ln(3)
        self.set_text_color(*_DARK)

    def kv(self, label: str, value: str, fill: bool = False) -> None:
        if fill:
            self.set_fill_color(*_LGRAY)
        self.set_font("Helvetica", "", 8)
        self.cell(45, 5.5, label, fill=fill)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 5.5, value, fill=fill, new_x="LMARGIN", new_y="NEXT")
        self.set_fill_color(*_WHITE)

    def stat_box(self, x: float, y: float, w: float, h: float,
                 label: str, value: str,
                 bg: tuple = _LGRAY, fg: tuple = _DARK) -> None:
        self.set_xy(x, y)
        self.set_fill_color(*bg)
        self.set_draw_color(*_BORDER)
        self.rect(x, y, w, h, style="FD")
        self.set_xy(x, y + 2)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*_GRAY)
        self.cell(w, 4, label, align="C")
        self.set_xy(x, y + 5.5)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*fg)
        self.cell(w, 7, value, align="C")
        self.set_text_color(*_DARK)
        self.set_fill_color(*_WHITE)

    def embed_image(self, buf: io.BytesIO, w_px: int, h_px: int,
                    x: float, y: float, max_w: float, max_h: float) -> float:
        """Inserta imagen y devuelve su altura real en mm."""
        w_mm, h_mm = _scale_image(w_px, h_px, max_w, max_h)
        self.image(buf, x=x, y=y, w=w_mm, h=h_mm)
        return h_mm


# ── API pública ────────────────────────────────────────────────────────────────

def generate_pdf(
    predio_id: str,
    predio_info: dict,
    date_from: date,
    date_to: date,
    ndvi_stats: dict,
    ndvi_png_bytes: bytes,
    ts_points: list,
    anomaly_stats: dict | None,
    anomaly_png_bytes: bytes | None,
) -> bytes:
    """
    Genera el PDF del reporte NDVI y devuelve los bytes.

    Args:
        predio_id: identificador del predio.
        predio_info: dict con nombre, hectareas, cultivo, region, comuna.
        date_from / date_to: período del reporte.
        ndvi_stats: dict con mean, min, max, std, valid_pixel_pct.
        ndvi_png_bytes: PNG coloreado del NDVI.
        ts_points: lista de TimeseriesPoint del servicio timeseries.
        anomaly_stats: dict con pct_stress, pct_normal, pct_above, baseline_months (o None).
        anomaly_png_bytes: PNG del z-score (o None).
    """
    periodo = (
        f"{date_from.day:02d} {_MONTH_ES[date_from.month]} {date_from.year}"
        f" - "
        f"{date_to.day:02d} {_MONTH_ES[date_to.month]} {date_to.year}"
    )
    pdf = _PDF(predio_info.get("nombre", predio_id), periodo)
    pdf.add_page()

    # ── Información del predio ────────────────────────────────────────────────
    pdf.section_title("Información del Predio")
    pdf.kv("Nombre", predio_info.get("nombre", predio_id), fill=True)
    pdf.kv("Region / Comuna",
           f"Region {predio_info.get('region', '-')}  |  {predio_info.get('comuna', '-')}")
    pdf.kv("Superficie", f"{predio_info.get('hectareas', '—')} ha", fill=True)
    pdf.kv("Cultivo", str(predio_info.get("cultivo", "—")).capitalize())
    pdf.kv("Período evaluado", periodo, fill=True)
    pdf.ln(6)

    # ── NDVI ─────────────────────────────────────────────────────────────────
    pdf.section_title("Índice de Vegetación (NDVI)")

    ndvi_buf, ndvi_w, ndvi_h = _png_to_buf(ndvi_png_bytes)
    img_y = pdf.get_y()
    img_h = pdf.embed_image(ndvi_buf, ndvi_w, ndvi_h,
                             x=MARGIN, y=img_y,
                             max_w=COL_W, max_h=65)

    # Tabla de stats a la derecha
    stats_x = MARGIN + COL_W + 6
    pdf.set_xy(stats_x, img_y)

    def _fmt(v: float | None, decimals: int = 3) -> str:
        return "—" if v is None else f"{v:.{decimals}f}"

    mean_v = ndvi_stats.get("mean")
    # Color según salud del cultivo
    if mean_v is not None:
        if mean_v >= 0.6:
            interp, interp_color = "Vegetación densa / viña sana", _GREEN
        elif mean_v >= 0.3:
            interp, interp_color = "Vegetación moderada", (202, 138, 4)
        elif mean_v >= 0:
            interp, interp_color = "Vegetación escasa / suelo", (234, 88, 12)
        else:
            interp, interp_color = "Agua o nubes dominantes", _RED
    else:
        interp, interp_color = "Sin datos", _GRAY

    rows = [
        ("NDVI Promedio", _fmt(mean_v), True),
        ("NDVI Mínimo",   _fmt(ndvi_stats.get("min")), False),
        ("NDVI Máximo",   _fmt(ndvi_stats.get("max")), True),
        ("Desvío estándar", _fmt(ndvi_stats.get("std")), False),
        ("Píxeles válidos", _fmt(ndvi_stats.get("valid_pixel_pct"), 1) + "%", True),
    ]
    for label, value, fill in rows:
        if fill:
            pdf.set_fill_color(*_LGRAY)
        pdf.set_xy(stats_x, pdf.get_y())
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(40, 5.5, label, fill=fill)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(COL_W - 40, 5.5, value, fill=fill, new_x="LMARGIN", new_y="NEXT")
        pdf.set_fill_color(*_WHITE)

    # Interpretación
    pdf.set_xy(stats_x, pdf.get_y() + 3)
    pdf.set_fill_color(*_LGRAY)
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*interp_color)
    pdf.cell(COL_W, 7, interp, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*_DARK)

    pdf.set_y(img_y + img_h + 4)
    pdf.ln(2)

    # ── Serie temporal ────────────────────────────────────────────────────────
    if ts_points:
        pdf.section_title(f"Serie Temporal NDVI ({len(ts_points)} meses)")
        chart_buf = _timeseries_chart(ts_points)
        chart_img = Image.open(chart_buf)
        chart_w, chart_h = chart_img.size
        chart_buf.seek(0)
        c_w, c_h = _scale_image(chart_w, chart_h, A4_W - 2 * MARGIN, 60)
        pdf.image(chart_buf, x=MARGIN, y=pdf.get_y(), w=c_w, h=c_h)
        pdf.ln(c_h + 5)

    # ── Anomalías ────────────────────────────────────────────────────────────
    if anomaly_stats and anomaly_png_bytes:
        pdf.section_title("Detección de Anomalías (Z-Score)")

        an_buf, an_w, an_h = _png_to_buf(anomaly_png_bytes)
        an_y = pdf.get_y()
        an_h_mm = pdf.embed_image(an_buf, an_w, an_h,
                                  x=MARGIN, y=an_y,
                                  max_w=COL_W, max_h=65)

        # Cajas de porcentajes
        box_x = MARGIN + COL_W + 6
        box_w = (COL_W - 4) / 3
        pdf.stat_box(box_x,           an_y,      box_w, 16, "Estrés",
                     f"{anomaly_stats.get('pct_stress', 0):.1f}%",
                     bg=(254, 226, 226), fg=_RED)
        pdf.stat_box(box_x + box_w + 2, an_y,    box_w, 16, "Normal",
                     f"{anomaly_stats.get('pct_normal', 0):.1f}%",
                     bg=_LGRAY, fg=_DARK)
        pdf.stat_box(box_x + 2*(box_w+2), an_y,  box_w, 16, "Sobre normal",
                     f"{anomaly_stats.get('pct_above', 0):.1f}%",
                     bg=(219, 234, 254), fg=_BLUE)

        pdf.set_xy(box_x, an_y + 20)
        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(*_GRAY)
        bl = anomaly_stats.get("baseline_months", 0)
        th = anomaly_stats.get("threshold", 2.0)
        pdf.cell(COL_W, 5, f"Baseline: {bl} mes{'es' if bl != 1 else ''}  |  Umbral: +/-{th}")
        pdf.set_text_color(*_DARK)

        pdf.set_y(an_y + max(an_h_mm, 30) + 4)

    return bytes(pdf.output())


def build_report(
    predio_id: str,
    date_from: date,
    date_to: date,
    ndvi_dir: Path,
    anomaly_dir: Path,
    predios_dir: Path,
) -> bytes:
    """
    Orquesta la recolección de datos y genera el PDF.

    Raises:
        FileNotFoundError: si el GeoTIFF NDVI del período no existe.
    """
    # Predio info
    geojson_path = predios_dir / f"{predio_id}.geojson"
    predio_info: dict = {}
    if geojson_path.exists():
        with geojson_path.open() as f:
            fc = json.load(f)
        predio_info = fc["features"][0]["properties"]

    # NDVI
    ndvi_tif = ndvi_dir / predio_id / f"{date_from}_{date_to}_NDVI.tif"
    if not ndvi_tif.exists():
        raise FileNotFoundError(
            f"GeoTIFF NDVI no encontrado para {predio_id} ({date_from} -> {date_to}). "
            "Ejecuta /compute primero."
        )

    import rasterio
    with rasterio.open(ndvi_tif) as ds:
        tags = ds.tags()

    def _tf(k: str) -> float | None:
        try:
            v = float(tags[k])
            return None if v != v else v
        except (KeyError, ValueError):
            return None

    ndvi_stats = {
        "mean": _tf("ndvi_mean"),
        "min":  _tf("ndvi_min"),
        "max":  _tf("ndvi_max"),
        "std":  _tf("ndvi_std"),
        "valid_pixel_pct": _tf("ndvi_valid_pixel_pct"),
    }
    ndvi_png, _ = ndvi_to_png(ndvi_tif)

    # Serie temporal
    ts_points = read_timeseries(ndvi_dir / predio_id)

    # Anomalía (opcional)
    anomaly_stats: dict | None = None
    anomaly_png: bytes | None = None
    zscore_tif = anomaly_dir / predio_id / f"{date_from}_{date_to}_zscore.tif"
    if zscore_tif.exists():
        with rasterio.open(zscore_tif) as ds:
            ztags = ds.tags()

        def _ztf(k: str) -> float | None:
            try:
                v = float(ztags[k])
                return None if v != v else v
            except (KeyError, ValueError):
                return None

        anomaly_stats = {
            "pct_stress":  _ztf("pct_stress"),
            "pct_normal":  _ztf("pct_normal"),
            "pct_above":   _ztf("pct_above"),
            "baseline_months": int(ztags.get("baseline_months", 0)),
            "threshold": float(ztags.get("threshold", 2.0)),
        }
        anomaly_png, _ = zscore_to_png(zscore_tif)

    logger.info("Generando PDF para %s (%s → %s)", predio_id, date_from, date_to)
    return generate_pdf(
        predio_id=predio_id,
        predio_info=predio_info,
        date_from=date_from,
        date_to=date_to,
        ndvi_stats=ndvi_stats,
        ndvi_png_bytes=ndvi_png,
        ts_points=ts_points,
        anomaly_stats=anomaly_stats,
        anomaly_png_bytes=anomaly_png,
    )
