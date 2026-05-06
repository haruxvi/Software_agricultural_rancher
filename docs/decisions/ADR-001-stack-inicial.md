# ADR-001 — Stack inicial del MVP

**Fecha:** 2026-05-06
**Estado:** Aceptado

## Contexto

Se necesita un stack que permita construir un MVP funcional de forma rápida,
con soporte geoespacial real y bajo costo de infraestructura inicial.

## Decisión

- **FastAPI** sobre Flask/Django: async nativo, validación automática con Pydantic,
  OpenAPI integrado. Permite exponer tiles NDVI y webhooks sin bloquear el event loop.
- **rasterio + GeoPandas** sobre GDAL directo: API Pythónica, documentación activa,
  integración directa con NumPy para cálculos NDVI.
- **sentinelhub-py** para Sentinel-2: SDK oficial de Copernicus Data Space,
  evita manejo manual de OAuth y rate limits.
- **PostgreSQL + PostGIS** sobre SQLite/SpatiaLite: necesario para consultas
  espaciales en producción; Render ofrece tier gratuito.
- **Supabase Auth** sobre JWT propio: reduce superficie de ataque en MVP;
  fácil migración posterior.
- **Render free tier** para deploy inicial: sin costo, suficiente para demos a clientes.

## Consecuencias

- rasterio requiere GDAL nativo: el entorno de desarrollo y el Dockerfile
  deben incluir librerías del sistema (libgdal-dev).
- WeasyPrint tiene dependencias de sistema (Pango, Cairo); se debe validar
  compatibilidad en el runner de Render.
- Supabase free tier tiene límite de 500 MB de base de datos y 50k MAU.
