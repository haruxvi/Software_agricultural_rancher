# Notas de deploy — AgroVista MVP

## Comando de inicio

```
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

## Variables de entorno a configurar en la plataforma

| Variable | Dónde conseguirla |
|---|---|
| `DATABASE_URL` | Dashboard de la BD (Railway, Supabase, PlanetScale…) — formato: `postgresql://user:pass@host:5432/db` |
| `SH_CLIENT_ID` | [Copernicus Data Space](https://dataspace.copernicus.eu) → OAuth Clients |
| `SH_CLIENT_SECRET` | Misma sección que el anterior |
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Supabase → Project Settings → API → anon/public key |
| `SUPABASE_JWT_SECRET` | Supabase → Project Settings → JWT → JWT Secret |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |

## Servicios externos a crear antes del primer deploy

1. **Supabase** — crear proyecto, habilitar Auth por email/contraseña, copiar las 3 variables de arriba
2. **PostgreSQL** — crear una base de datos (Railway la crea con un click, o usar el Postgres de Supabase)
3. **CDSE** — cuenta en dataspace.copernicus.eu + crear OAuth client

## Archivos estáticos / datos

- `data/predios/` está en el repo → se despliega con el código
- `data/raw/`, `data/ndvi/`, `data/anomaly/` son efímeros — se recrean en cada inicio pero los archivos TIF no persisten
- Para persistencia real: montar un volumen y cambiar `DATA_DIR` en `backend/routers/ndvi.py`

## Railway (notas rápidas)

- Detecta Python automáticamente con `.python-version`
- Agregar las variables en Settings → Variables
- Si conectas una PostgreSQL de Railway, la variable `DATABASE_URL` se inyecta automáticamente

## Vercel (notas rápidas)

- Vercel es serverless — FastAPI necesita un adaptador. Agregar `vercel.json`:
  ```json
  {
    "builds": [{ "src": "backend/main.py", "use": "@vercel/python" }],
    "routes": [{ "src": "/(.*)", "dest": "backend/main.py" }]
  }
  ```
- El filesystem es **completamente efímero** en Vercel (funciones sin estado) — las descargas de Sentinel no van a funcionar sin almacenamiento externo (S3, Supabase Storage)
- Railway es mejor fit para esta app

---

> **Nota MVP:** este sistema es validación de concepto.
> El proyecto real tendrá almacenamiento en S3/GCS para los GeoTIFFs,
> procesamiento asíncrono (colas), y base de datos con PostGIS real.
