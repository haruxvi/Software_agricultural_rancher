# AgroVista (MVP)

Plataforma SaaS de monitoreo satelital para predios agrícolas en Chile.
NDVI sobre Sentinel-2 + alertas por anomalía + reporte PDF — MVP para viñas en Colchagua/Curicó.

[![CodeQL](https://github.com/haruxvi/Software_agricultural_rancher/actions/workflows/codeql.yml/badge.svg)](https://github.com/haruxvi/Software_agricultural_rancher/actions/workflows/codeql.yml)
[![Security SAST](https://github.com/haruxvi/Software_agricultural_rancher/actions/workflows/security.yml/badge.svg)](https://github.com/haruxvi/Software_agricultural_rancher/actions/workflows/security.yml)
[![Dependabot enabled](https://img.shields.io/badge/dependabot-enabled-025e8c?logo=dependabot)](https://github.com/haruxvi/Software_agricultural_rancher/security/dependabot)

## Stack

- **Backend**: Python 3.12 + FastAPI
- **Geoespacial**: rasterio, GeoPandas, Shapely
- **Datos satelitales**: Sentinel-2 vía Copernicus Data Space
- **Auth**: Supabase Auth (JWT HS256)
- **BD**: PostgreSQL 16 + PostGIS
- **Frontend**: HTML + Leaflet.js + Tailwind
- **PDF**: WeasyPrint
- **Deploy MVP**: Render free tier

## Setup rápido

```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # completar SUPABASE_JWT_SECRET, DATABASE_URL, etc.
alembic upgrade head
uvicorn backend.main:app --reload --port 8000
```

## Tests y lint

```bash
pytest backend/tests/
ruff check backend/ && ruff format backend/
```

## Seguridad

Cada PR pasa automáticamente Bandit (HIGH+), pip-audit (CVEs) y Semgrep (ERROR) antes de merge.
Ver [ADR-011](docs/decisions/ADR-011-sast-ci.md) para el razonamiento de la arquitectura de seguridad.
