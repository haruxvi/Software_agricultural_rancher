# ADR-004 — Servir NDVI como PNG para imageOverlay en Leaflet

**Fecha:** 2026-05-06
**Estado:** Aceptado

## Contexto

Se necesita exponer el NDVI calculado de forma que Leaflet pueda mostrarlo
sobre el mapa. Las alternativas evaluadas:

1. **PNG con imageOverlay** — imagen georreferenciada, un solo request HTTP.
2. **XYZ tiles (TMS)** — requiere servidor de tiles (TiTiler, GeoServer), fuera del MVP.
3. **GeoJSON de contornos** — pérdida de detalle por rasterización; complejo de generar.
4. **Protobuf / MVT** — overkill para imágenes de 130×130 px.

## Decisión

Servir el NDVI como **PNG RGBA** via `GET /ndvi/predios/{id}/image` y usarlo
en Leaflet con `L.imageOverlay(url, bounds)`.

- **Colormap RdYlGn** (matplotlib): estándar en teledetección agrícola.
  Rojo = vegetación débil/agua, verde = vegetación densa.
- **Canal alpha = 0** en píxeles nodata: el mapa base se ve "debajo" de las nubes.
- **`GET /ndvi/predios/{id}/meta`**: devuelve `bounds_leaflet` ([[S,W],[N,E]])
  y estadísticas desde los tags del GeoTIFF, sin regenerar el PNG.

## Consecuencias

- El PNG se genera en memoria (sin caché en disco). Para predios grandes o
  muchos usuarios simultáneos habrá que agregar caché HTTP (ETag/Cache-Control).
- El GeoTIFF NDVI almacena todas las stats en sus tags (mean, min, max, std,
  valid_pixel_pct) para que `/meta` no requiera releer los píxeles.
- El tamaño del PNG para 130×130 px RGBA ≈ 5-15 KB; aceptable para MVP.
- En el Paso 4 (Leaflet), el frontend llama primero a `/meta` para obtener
  los bounds y luego carga el PNG con `L.imageOverlay`.
