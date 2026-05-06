import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from backend.services.report import build_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report", tags=["report"])

DATA_DIR    = Path("data")
NDVI_DIR    = DATA_DIR / "ndvi"
ANOMALY_DIR = DATA_DIR / "anomaly"
PREDIOS_DIR = DATA_DIR / "predios"


@router.get("/predios/{predio_id}/pdf")
def get_report_pdf(
    predio_id: str,
    date_from: date = Query(...),
    date_to: date = Query(...),
) -> Response:
    """Genera y descarga el reporte PDF de NDVI para el período indicado."""
    try:
        pdf_bytes = build_report(
            predio_id=predio_id,
            date_from=date_from,
            date_to=date_to,
            ndvi_dir=NDVI_DIR,
            anomaly_dir=ANOMALY_DIR,
            predios_dir=PREDIOS_DIR,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Error generando PDF para %s", predio_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    filename = f"agrovista_{predio_id}_{date_from}_{date_to}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
