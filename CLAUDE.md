# AgroVista — Plataforma de Agricultura de Precisión (MVP)

## Contexto del proyecto

SaaS para monitoreo satelital de predios agrícolas en Chile.
Cliente objetivo inicial: viñas premium en Colchagua/Curicó (VI y VII Región).
Caso de uso v0: NDVI sobre Sentinel-2 + alertas por anomalía + reporte PDF.

Este es un proyecto personal del owner del repo, construido fuera del horario y
recursos de su empleo actual (rubro distinto, no relacionado con agro).

## Stack

- Backend: Python 3.12 + FastAPI
- Geoespacial: rasterio, GeoPandas, Shapely
- Datos satelitales: Sentinel-2 vía Copernicus Data Space (sentinelhub-py)
- Meteorología: NASA POWER API
- BD: PostgreSQL 16 + PostGIS
- Frontend: HTML + Leaflet.js + Tailwind (CDN en MVP)
- PDF: WeasyPrint
- Auth: Supabase Auth
- Deploy MVP: Render free tier

## Estructura

backend/        FastAPI app (routers, services, db)
frontend/       HTML estático con Leaflet
data/predios/   GeoJSON de predios de prueba
docs/decisions/ ADRs con fecha y razón

## Comandos

- `python3.12 -m venv venv && source venv/bin/activate` — setup
- `pip install -r requirements.txt` — deps
- `uvicorn backend.main:app --reload --port 8000` — dev server
- `pytest backend/tests/` — tests
- `ruff check backend/ && ruff format backend/` — lint
- `alembic upgrade head` — migraciones

## Convenciones

- Type hints obligatorios en funciones públicas
- Pydantic para I/O del API
- Logging estructurado (nada de `print`)
- Manejo explícito de errores con HTTPException
- Tests unitarios para cálculos (NDVI, anomalías)
- Variables en inglés, comentarios en español OK
- Conventional Commits

## Reglas de seguridad / IP

- Credenciales solo en .env (en .gitignore)
- NO usar nomenclatura, schemas, lógica ni patrones del empleador del owner
- Estructuras inspiradas en otros sistemas DEBEN derivarse de fuentes públicas
- Datos de prueba: solo fixtures sintéticos, nunca clientes reales
- Documentar decisiones de arquitectura en docs/decisions/

## Roadmap MVP (no saltar etapas)

1. Bajar 1 imagen Sentinel-2 de un predio de prueba
2. Calcular NDVI con rasterio
3. Servir NDVI por API
4. Mostrar NDVI en Leaflet
5. Serie temporal 12 meses
6. Detección anomalías con z-score
7. Generar PDF con WeasyPrint
8. Auth Supabase
9. Deploy Render
10. Dominio NIC Chile

## Out of scope (NO construir todavía)

- Microservicios / Kubernetes / AWS
- Modelos de ML profundos (CNN)
- App móvil nativa
- Hardware (drones, sensores GPS, collares)
- Integración SAG/SIPEC
- Trazabilidad ganadera
