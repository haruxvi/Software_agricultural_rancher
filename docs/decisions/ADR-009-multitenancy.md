# ADR-009 — Control de acceso por recurso (multitenancy / IDOR)

**Fecha:** 2026-05-08  
**Estado:** Aceptado

## Contexto

Cualquier usuario autenticado podía leer cualquier `predio_id` en los endpoints NDVI y PDF.
Esto es una vulnerabilidad IDOR (Insecure Direct Object Reference): no se verificaba que el
`predio_id` del path perteneciera al usuario que hacía la solicitud.

## Decisión

Se implementa una tabla `user_predios` que registra qué usuario tiene ownership sobre qué predio:

```
user_predios(id UUID PK, user_id UUID, predio_id VARCHAR(64), role VARCHAR(50), created_at TIMESTAMP)
UNIQUE(user_id, predio_id)
```

La verificación se concentra en la FastAPI dependency `get_user_predio` (en `backend/auth.py`):

1. Valida el JWT del usuario (`get_current_user`).
2. Valida el formato de `predio_id` con regex `^[a-zA-Z0-9_-]{1,64}$` (previene path traversal).
3. Consulta `user_predios` vía `user_owns_predio()` del servicio de autorización.
4. Si no existe registro → HTTP 403. Si no hay token → HTTP 401.

Todos los endpoints que reciben `predio_id` deben declararlo como:
```python
predio_id: str = Depends(get_user_predio)
```

En modo desarrollo (`SUPABASE_JWT_SECRET` vacío) se omite la validación para facilitar el desarrollo local.

## Alternativas consideradas

- **Filtros inline en cada endpoint**: rechazada — duplica lógica y es fácil olvidarlo en endpoints nuevos.
- **Row-Level Security en PostgreSQL**: válida para producción avanzada, pero agrega complejidad de migración y requiere Supabase RLS configurado. Se puede adoptar en el futuro sobre esta misma tabla.
- **Scope en JWT**: requeriría tokens custom de Supabase. Exceso de complejidad para el MVP.

## Consecuencias

- **Positivas:** elimina IDOR, lógica de autorización centralizada y testeable, compatible con futuros roles (viewer, agrónomo, etc.).
- **Negativas:** requiere seed manual de `user_predios` para cada usuario de prueba.
- **Neutras:** en dev mode el comportamiento no cambia.
