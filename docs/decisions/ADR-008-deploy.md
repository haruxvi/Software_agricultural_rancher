# ADR-008: Deploy del MVP

**Fecha:** 2026-05-07
**Estado:** Aceptado

## Decisiones tomadas para producción

- Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Python 3.12 (`.python-version` en la raíz)
- El servicio sirve el frontend estático + la API desde el mismo proceso (no hay separación)
- `lifespan` en FastAPI crea los directorios de datos en cada inicio (filesystem puede ser efímero)

## Variables de entorno requeridas

Ver `.env.example` para la lista completa. En producción todas deben setearse en el
dashboard de la plataforma — nunca en el código.

## Dependencias externas a conectar

1. **Supabase** — auth + (opcional) base de datos
2. **Copernicus Data Space (CDSE)** — imágenes Sentinel-2
3. **PostgreSQL** — actualmente sin uso en los endpoints, preparado para siguientes etapas

## Limitación de filesystem

El directorio `data/` (excepto `data/predios/`) no persiste entre reinicios en plataformas
con filesystem efímero. Los archivos TIF generados se pierden; el usuario debe
re-descargar/recalcular. Para persistencia real: montar un volumen externo y cambiar
`DATA_DIR` en los routers a esa ruta.

## Nota MVP

Este deploy es validación de concepto. El sistema real implicará arquitectura distribuida,
almacenamiento de objetos (S3/GCS) para los GeoTIFFs, y procesamiento asíncrono de colas.
