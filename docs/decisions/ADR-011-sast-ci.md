# ADR-011 — Defense in depth: SAST en CI antes de merge

**Fecha:** 2026-05-11
**Estado:** Aceptado
**Autores:** Vicente Donoso

---

## Contexto

AgroVista procesa coordenadas geoespaciales, datos satelitales y emite JWTs de
Supabase. Un bug de seguridad introducido silenciosamente en un PR podría exponer
datos de predios de múltiples clientes (IDOR) o permitir inyección de rutas.

El repositorio es de un solo desarrollador — no hay revisores de seguridad
dedicados. Se necesita una red de seguridad automatizada que corra en cada push
y PR sin costo adicional.

---

## Decisión

**Cuatro capas de análisis estático, todas corriendo en GitHub Actions:**

### 1. Bandit (`.github/workflows/security.yml`)
- Analiza `backend/` contra ~100 checks de seguridad Python (OWASP-alineados)
- CI falla solo en **HIGH** severity — reduce ruido sin ocultar riesgos reales
- Config `.bandit` excluye `tests/` (assert false-positives) y establece baseline MEDIUM para correr manualmente

### 2. pip-audit (`.github/workflows/security.yml`)
- Consulta OSV Database por CVEs en `requirements.txt`
- Corre en cada PR — dependencia con CVE crítico bloquea merge automáticamente

### 3. Semgrep (`.github/workflows/security.yml`)
- Auto config: detecta lenguaje y aplica ruleset apropiado (python, FastAPI patterns)
- Falla CI en severity **ERROR** (equivale a HIGH/CRITICAL en Semgrep)
- `.semgrepignore` excluye `tests/` y `data/` (archivos binarios / fixtures)

### 4. CodeQL (`.github/workflows/codeql.yml`)
- Suite `security-extended`: cobertura más amplia que la default
- Análisis semanal + en cada push a master
- Resultados en GitHub Security → Code scanning alerts (no bloquea CI directamente)

### Capa complementaria: ruff reglas S
- `pyproject.toml` habilita ruleset "S" (bandit integrado en ruff)
- Corre localmente con `ruff check` — feedback instantáneo al escribir código
- Falsos positivos documentados en `per-file-ignores` con justificación

### GitHub UI (activar manualmente)
- Dependabot alerts + security updates: CVEs en dependencias con PRs automáticos
- Secret scanning + Push protection: bloquea secrets en commits antes del push

---

## Alternativas descartadas

| Alternativa | Razón de descarte |
|---|---|
| Solo Bandit | No detecta CVEs en dependencias ni patrones complejos como Semgrep |
| Snyk / SonarQube | Requieren cuenta de pago para proyectos privados |
| Solo CodeQL | No detecta CVEs en deps, ejecución más lenta (5-10 min vs 1-2 min) |
| Pre-commit hooks locales | No garantiza que todos los devs los corran; CI es la fuente de verdad |

---

## Consecuencias

- **Positivo**: cobertura multicapa — una herramienta detecta lo que otra puede perder
- **Positivo**: feedback en < 2 min para bandit/semgrep, sin costo en GitHub Free
- **Positivo**: pip-audit bloquea dependencias con CVEs conocidos antes de merge
- **Negativo**: tiempo de CI aumenta ~90 s por job (3 jobs paralelos ≈ 90 s total)
- **Negativo**: falsos positivos ocasionales requieren `# noqa` o `per-file-ignores` justificados
- **Trade-off aceptado**: CodeQL no bloquea CI directamente (crea alertas, no falla el workflow) para evitar bloqueos en el periodo de onboarding de las queries
