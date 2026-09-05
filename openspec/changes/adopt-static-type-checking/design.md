## Context

Estado actual (verificado): `pyproject.toml` sólo configura `[tool.ruff]` con `select = ["E", "F", "I", "UP", "B"]`; no hay `[tool.mypy]`, `[tool.pyright]` ni `py.typed`. El stack usa `pydantic>=2.9` y `sqlalchemy[asyncio]>=2.0.36`, ambos con tipado completo, y `target-version = "py314"`. El código async mezcla `Optional`, `Mapping`, `Sequence` y genéricos en `recallum/memory/service.py` y `recallum/db/repositories/`, zonas donde los errores de clase (ver el hallazgo 3 del plan) tienen tipos que un checker atraparía.

## Goals / Non-Goals

**Goals:**

- Que los errores de tipo se detecten antes de ejecución, en local y en CI.
- Que la adopción no bloquee el desarrollo: modo gradual con baseline explícita.

**Non-Goals:**

- No se reescribe código para "satisfacer al checker" cuando el tipado dinámico es intencional (p.ej. manejo de `IntegrityError.orig`, tipos de driver); esos casos se suprimen con anotación puntual y justificación.
- No se añade chequeo estricto a `tests/` en la primera iteración si el coste es alto.

## Decisions

1. **mypy sobre pyright como punto de partida.** Razón: la configuración en `pyproject.toml` es nativa de mypy, y la adopción gradual (`follow_imports`, `disallow_untyped_defs` por módulo) está bien documentada para SQLAlchemy+Pydantic. Si el barrido inicial muestra fricción con los plugins de SQLAlchemy, se reconsidera pyright en una iteración posterior sin cambiar CI.
2. **Modo estricto por paquete, no global.** `recallum/` entra en modo casi estricto (`disallow_untyped_defs`, `warn_return_any`, `strict_optional`) desde el primer día; `tests/` queda en modo permisivo explícito con fecha de revisión. Una baseline de errores existentes se suprime con `# type: ignore` puntuales contados, no con `disable_error_code` globales.
3. **Paso bloqueante en CI.** El workflow `.github/workflows/ci.yml` gana un paso que falla el build en error de tipo, igual que el de tests, para evitar regresiones silenciosas.

## Baseline medida (2026-09-05)

Barrido real: mypy con plugins pydantic+sqlalchemy reportó 134 errores en 23 archivos en modo estricto
global. Tras relajar los módulos con falsos positivos de framework (app, container, mcp, web, db,
migrations, cli, diagnostics) quedaron 18 errores reales en 9 archivos. Dos se corrigieron en código
(`telemetry/repository.py` rowcount, `memory/context.py` dict.get Literal) y el resto quedó suprimido
por código de error y archivo en `pyproject.toml` como baseline explícita y contada, pendiente de
resolución en cambios posteriores.

## Risks / Trade-offs

- **Ruido inicial**: el primer barrido sobre 20k líneas puede arrojar decenas de errores reales o falsos positivos de driver. Mitigación: baseline contada y modo gradual, no big-bang.
- **Velocidad de CI**: mypy añade tiempo. Mitigación: cache de `.mypy_cache` en el workflow y ejecución sólo sobre el paquete, no sobre tests.
