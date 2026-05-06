# ADR-005 — Detección de Anomalías NDVI con Z-Score Pixel a Pixel

**Fecha:** 2026-05-06
**Estado:** Aceptado

## Contexto

Se necesita detectar zonas de la viña con NDVI inusualmente bajo (estrés hídrico,
enfermedad, plaga) o alto (crecimiento inusual) respecto a su comportamiento histórico.

## Decisión

Implementar z-score pixel a pixel sobre la serie temporal disponible:

```
z(x,y) = (NDVI_objetivo(x,y) − μ_baseline(x,y)) / σ_baseline(x,y)
```

Donde `μ` y `σ` se calculan con **todos los meses excepto el objetivo** como baseline.

- **Umbral configurable** (default ±2.0): |z| > threshold → anomalía.
- **std=0**: sin variabilidad histórica → nodata (no se puede calcular z-score).
- **Mínimo 3 meses** de baseline para que σ sea estadísticamente válido.
- **ddof=1** (varianza muestral) para baseline finito.

## Clasificación de píxeles

| z-score         | Clase        | Color (RdBu)   |
|-----------------|--------------|----------------|
| z < −threshold  | Estrés       | Rojo           |
| ±threshold      | Normal       | Blanco         |
| z > +threshold  | Sobre normal | Azul           |

## Alternativas descartadas

- **Diferencia simple** (NDVI − media): no normaliza por variabilidad estacional.
- **BFAST / regresión fenológica**: más preciso pero requiere >3 años de datos.
- **Isolation Forest / ML**: out of scope para MVP.

## Consecuencias

- Con 12 meses sintéticos de baseline el z-score es orientativo; en producción
  se recomienda mínimo 3 años de datos reales.
- El GeoTIFF z-score se guarda en `data/anomaly/{predio_id}/` con los porcentajes
  de estrés/normal/sobre en los tags para que `/meta` no releer píxeles.
- En el frontend el overlay de anomalía es independiente del overlay NDVI
  y puede mostrarse/ocultarse por separado.
