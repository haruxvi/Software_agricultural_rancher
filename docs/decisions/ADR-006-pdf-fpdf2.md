# ADR-006 — Generacion de PDF con fpdf2 (en lugar de WeasyPrint)

**Fecha:** 2026-05-06
**Estado:** Aceptado

## Contexto

El roadmap indicaba WeasyPrint para generar PDFs. WeasyPrint requiere las
bibliotecas de sistema Pango y GObject (GTK), que no estan disponibles en
Windows sin instalar el runtime GTK (msys2 o instalador GTK4 para Windows).
En el entorno de desarrollo actual (Windows 11) la importacion falla con
"cannot load library 'libgobject-2.0-0'".

## Decision

Usar **fpdf2** (pure Python, sin dependencias de sistema) para el MVP:

- Funciona en Windows, macOS y Linux sin configuracion adicional.
- API directa: se construye el PDF celda a celda con control total del layout.
- Las imagenes (mapa NDVI, mapa z-score, grafico serie temporal) se insertan
  como PNG en memoria (BytesIO), sin pasar por disco.
- El grafico de serie temporal se genera con **matplotlib (backend Agg)**,
  tambien sin pantalla.

## Contenido del reporte

1. Header con nombre del predio y periodo evaluado.
2. Tabla de informacion del predio (region, comuna, hectareas, cultivo).
3. Mapa NDVI + tabla de estadisticas (media, min, max, std, pixeles validos).
4. Grafico de serie temporal de 12 meses (matplotlib).
5. Mapa de anomalias z-score + cajas % estres / normal / sobre (opcional).
6. Footer con fecha de generacion.

## Consecuencias

- WeasyPrint sigue en requirements.txt para uso en produccion Linux (Render),
  donde las dependencias de sistema si estan disponibles.
- fpdf2 usa Helvetica (Latin-1): se evitan caracteres Unicode fuera del rango
  basico (em dash, puntos especiales). Para soporte Unicode completo se puede
  agregar una fuente TrueType (DejaVuSans) en una iteracion futura.
- El PDF se sirve como descarga directa (Content-Disposition: attachment)
  desde GET /report/predios/{id}/pdf?date_from=&date_to=.
