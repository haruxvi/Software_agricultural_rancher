# ADR-010 — Política de autenticación fail-closed

**Fecha:** 2026-05-11
**Estado:** Aceptado
**Autores:** Vicente Donoso

---

## Contexto

El backend AgroVista usa Supabase Auth para emitir JWT. Durante el desarrollo
local no siempre se configura `SUPABASE_JWT_SECRET`, y la primera implementación
usaba esa ausencia como señal para retornar un usuario ficticio en **cualquier**
entorno.

El riesgo: si `SUPABASE_JWT_SECRET` no se carga en producción (variable de
entorno mal configurada, typo en nombre, secreto rotado sin redeploy), la app
arranca, responde 200 a todos los requests y expone datos de todos los predios
sin autenticación real.

---

## Decisión

**Fail-closed:** la app solo permite el modo "sin secret = usuario ficticio" cuando
`settings.environment == "development"`. En cualquier otro entorno:

1. **Al arranque** (`config.py` `model_validator`): si `environment == "production"`
   y faltan `SUPABASE_JWT_SECRET`, `SUPABASE_URL` o `DATABASE_URL`, la app lanza
   `ValidationError` y no levanta.

2. **En `get_current_user`**: si `supabase_jwt_secret` está vacío fuera de
   `development`, log CRITICAL + HTTP 503.

3. **En `get_user_predio`**: misma lógica defensiva.

Además se endurecen las validaciones JWT:

- **Issuer**: cuando `supabase_url` está configurado, se valida que el JWT
  provenga de `<supabase_url>/auth/v1`. Rechaza tokens de proyectos Supabase
  distintos o de issuers arbitrarios.
- **Leeway**: 30 s de tolerancia a desfase de reloj entre servidor y Supabase.
- **Sub**: token sin claim `sub` → HTTP 401 explícito (no llega a `get_user_predio`).

---

## Alternativas descartadas

| Alternativa | Razón de descarte |
|---|---|
| Mantener fail-open | Un secreto faltante pasaría desapercibido en staging/prod |
| Variable separada `AUTH_BYPASS=true` | Más superficie de configuración; mismo riesgo si se activa accidentalmente |
| Deshabilitar bypass completamente | Hace el onboarding local más pesado sin ganar seguridad material |

---

## Consecuencias

- **Positivo**: misconfiguraciones de producción son visibles inmediatamente
  (la app no levanta o devuelve 503), no silenciosas.
- **Positivo**: tokens de proyectos Supabase cruzados o forjados son rechazados.
- **Negativo**: el desarrollador local debe configurar `environment=development`
  explícitamente si quiere usar el bypass (es el valor por defecto, así que
  solo afecta si alguien sobreescribe esa variable).
- **Negativo**: si `SUPABASE_URL` no se configura en staging, la validación de
  issuer se omite silenciosamente (trade-off aceptado vs. bloquear staging).
