import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.routers import ndvi, report

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Render tiene filesystem efímero — crear directorios en cada inicio
    for subdir in ("predios", "raw", "ndvi", "anomaly"):
        (Path("data") / subdir).mkdir(parents=True, exist_ok=True)
    logger.info("Directorios de datos verificados")
    yield


app = FastAPI(
    title="AgroVista API",
    description="Monitoreo satelital de predios agrícolas — MVP",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(ndvi.router)
app.include_router(report.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}


@app.get("/config")
def public_config() -> dict:
    """Expone claves públicas de Supabase para el cliente JS (anon key es pública por diseño)."""
    return {
        "supabase_url": settings.supabase_url,
        "supabase_anon_key": settings.supabase_anon_key,
    }


# Archivos estáticos — montar DESPUÉS de todas las rutas API
# Solo se expone data/predios/ (GeoJSON de predios); los TIF generados no son públicos.
app.mount("/data/predios", StaticFiles(directory="data/predios"), name="predios")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
