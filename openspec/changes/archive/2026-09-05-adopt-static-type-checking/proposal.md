## Why

El repo no tiene chequeo de tipos estático: sólo ruff con reglas E/F/I/UP/B (`pyproject.toml`). Con Pydantic 2 y SQLAlchemy 2 completamente tipados, y con código async que mezcla `Optional`, genéricos y protocolos (por ejemplo la clasificación de excepciones del cambio `harden-error-classification`, o las uniones opcionales en las firmas de `remember`/`recall`/`context`), los errores de tipo actuales sólo emergen en tiempo de ejecución. Ruff no detecta una rama que devuelve `None` donde el llamador espera `StrictPositiveLimit`, ni un campo de esquema que desaparece silenciosamente.

## What Changes

- Se adopta un chequeador de tipos (mypy o pyright; decisión en design) configurado en modo estricto gradual: estricto en el paquete `recallum/`, permisivo en `tests/` si el coste de estricto total es alto.
- El chequeo se añade a la cadena de calidad local y a CI (`.github/workflows/ci.yml`) como paso bloqueante.
- Se corrigen los errores de tipo existentes que el primer barrido revele, o se establece una baseline suprimida explícita y contada, nunca una supresión global sin listar.

## Capabilities

### New Capabilities

(ninguna — cambio de tooling, sin cambio de comportamiento; declarado `skip_specs` en `.openspec.yaml`)

### Modified Capabilities

(ninguna)

## Impact

- Tooling: `pyproject.toml` (configuración del chequeador y dev-dependency), `.github/workflows/ci.yml`, cualquier `py.typed`/stubs necesarios para SQLAlchemy/asyncpg.
- Código: correcciones de tipado localizadas en `recallum/` donde el barrido inicial encuentre violaciones reales.
- Sin cambios en la superficie MCP ni en specs.
