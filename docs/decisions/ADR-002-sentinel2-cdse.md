# ADR-002 — Descarga de Sentinel-2 vía Copernicus Data Space (CDSE)

**Fecha:** 2026-05-06
**Estado:** Aceptado

## Contexto

Se necesita acceso a imágenes Sentinel-2 L2A (reflectancia de superficie) para
calcular NDVI sobre predios. Las opciones evaluadas fueron:

1. **Copernicus Data Space Ecosystem (CDSE)** vía sentinelhub-py
2. **Google Earth Engine** (requiere aprobación de cuenta y cliente OAuth pesado)
3. **AWS Open Data** (S3 requiere parsing manual de STAC + descarga de tiles)

## Decisión

Usar **CDSE + sentinelhub-py** porque:
- API REST con OAuth2, credenciales simples (client_id + secret).
- sentinelhub-py abstrae mosaicking, reproyección y filtro por nubosidad.
- Cuenta gratuita de CDSE incluye cuota suficiente para MVP (procesamiento por área).
- Evalscript permite filtrar píxeles nubosos con SCL band en el servidor,
  reduciendo datos descargados.

## Detalles de implementación

- **Bandas descargadas:** B04 (rojo, 665 nm) y B08 (NIR, 842 nm), 10 m de resolución.
- **Mosaicking:** `leastCC` — prioriza la escena con menor cobertura de nubes.
- **Máscara de nubes:** SCL classes 3 (shadow), 8, 9 (nubes), 10 (cirrus) → nodata=-9999.
- **Formato de salida:** GeoTIFF float32, EPSG:4326, 2 bandas (B04=1, B08=2).
- **Ruta:** `data/raw/{predio_id}/{date_from}_{date_to}_B04B08.tif`

## Consecuencias

- Los archivos .tif están excluidos de git (`.gitignore`). Para CI se usan
  imágenes sintéticas generadas con NumPy.
- Si la cobertura de nubes es alta en todo el rango, la API devuelve lista vacía;
  el servicio lanza `ValueError` con mensaje descriptivo.
- La cuota gratuita de CDSE se mide en Processing Units (PU). Un bbox de 45 ha
  a 10 m consume ~1 PU por descarga.
