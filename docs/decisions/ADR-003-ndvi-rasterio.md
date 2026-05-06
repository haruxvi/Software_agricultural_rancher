# ADR-003 — Cálculo de NDVI con rasterio + NumPy

**Fecha:** 2026-05-06
**Estado:** Aceptado

## Contexto

Se necesita calcular NDVI pixel a pixel sobre imágenes de ~130×130 px (45 ha a 10 m).

## Decisión

Implementar `compute_ndvi()` con rasterio + NumPy puro:

```
NDVI = (B08 - B04) / (B08 + B04)
```

- **rasterio** para lectura/escritura de GeoTIFF preservando CRS y transform.
- **NumPy vectorizado** para el cálculo; evita loops Python, suficiente para el
  tamaño de imagen del MVP.
- **Máscara de nodata** aplicada antes de la división: píxeles nubosos (SCL)
  marcados en el evalscript de descarga quedan como nodata=-9999 en el NDVI.
- **Denominador cero** (B04 = B08 = 0) tratado como nodata, no como NaN/inf,
  para compatibilidad con SIG (QGIS, ArcGIS).

## Consecuencias

- Para imágenes grandes (>2000×2000) habría que procesar por chunks con
  `rasterio.windows`; no es necesario en el MVP.
- El GeoTIFF de salida hereda el profile del input (CRS, transform, driver),
  lo que simplifica la visualización en Leaflet (Paso 4).
- Los tests unitarios usan fixtures NumPy sintéticos: sin dependencia de
  Sentinel Hub ni archivos reales, corren en CI sin credenciales.
