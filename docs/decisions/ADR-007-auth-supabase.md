# ADR-007: Autenticación con Supabase Auth

**Fecha:** 2026-05-07
**Estado:** Aceptado

## Contexto

La plataforma MVP necesita proteger los endpoints de API (NDVI, anomalías, reportes).
El stack ya incluía `supabase==2.15.2` y `python-jose[cryptography]` como dependencias,
y las variables `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` estaban
preconfiguradas en `config.py`.

## Decisión

Usar Supabase Auth con email/contraseña:

- **Frontend:** `@supabase/supabase-js` vía CDN maneja login, signup, logout y
  refresco automático de tokens (access token caduca cada hora, refresh token persiste).
- **Backend:** `python-jose` con HS256 valida el JWT de Supabase contra
  `SUPABASE_JWT_SECRET` en la dependencia `get_current_user` de FastAPI.
- **Protección de rutas:** dependencia aplicada a nivel de router en `/ndvi/*` y
  `/report/*`. Los endpoints `/health`, `/config` y los archivos estáticos son públicos.
- **Config pública:** endpoint `GET /config` expone `supabase_url` y `supabase_anon_key`.
  Estas claves están diseñadas por Supabase para ser públicas (el anon key solo permite
  acceso a filas con RLS o funciones permitidas).
- **Imágenes en Leaflet:** como `<img>` no soporta headers personalizados, las imágenes
  NDVI y z-score se descargan con `authFetch` y se sirven al overlay como `blob://` URL.
- **Modo desarrollo:** si `SUPABASE_JWT_SECRET` está vacío, el backend omite la
  validación JWT (retorna usuario ficticio). Si `SUPABASE_URL` está vacío, el frontend
  omite el overlay de auth.

## Consecuencias

- Todos los endpoints bajo `/ndvi/*` y `/report/*` requieren `Authorization: Bearer <token>`.
- Gestión de usuarios disponible tanto en el dashboard de Supabase como desde la app.
- El PDF se descarga via `authFetch` + blob link en lugar de `window.open` directo,
  lo que requiere que el PDF quepa en memoria del browser (aceptable para MVP).
- Signup con email de confirmación habilitado en Supabase mostrará mensaje de
  "revisa tu correo" en lugar de iniciar sesión directamente.
