import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routers import ndvi, report

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AgroVista API",
    description="Monitoreo satelital de predios agrícolas — MVP",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(ndvi.router)
app.include_router(report.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


# Archivos estáticos — montar DESPUÉS de todas las rutas API
# para que el catch-all de "/" no intercepte endpoints.
app.mount("/data", StaticFiles(directory="data"), name="data")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
