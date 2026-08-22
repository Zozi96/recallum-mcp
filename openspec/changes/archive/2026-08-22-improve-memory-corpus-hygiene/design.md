## Context

Similares, stale queue, reconfirm, update y merge ya existen. La fricción es guía y, en self-service, superficie HTTP para higiene sin vectores. El producto prohíbe auto-resolver contradicciones.

## Goals / Non-Goals

**Goals:**
- Criterio normativo merge-vs-update y desenlace stale obligatorio en guías/prompts/skill.
- Endurecer texto de `stale-review` y `capture-scan`.
- Exponer cola stale y vecinos en self-service si la API web aún no los cubre, reutilizando semántica de dominio.

**Non-Goals:**
- Auto-merge, auto-forget, cambiar `similar_min_similarity` por defecto.
- Ranking, grafo completo por MCP, o nuevas herramientas MCP.

## Decisions

- **Servidor informativo, agente decisivo**: el runtime no cambia la semántica de similares; el change es mayormente guía + self-service.
- **Self-service**: añadir endpoints de lectura (y mutaciones ya existentes si faltan) alineados a MCP; no duplicar lógica fuera de `MemoryService`.
- **Idioma**: memorias y merge content siguen en inglés; la guía de higiene puede estar en el idioma del skill del repo.

## Risks / Trade-offs

- [Guía más larga → menos cumplimiento] → Mantener reglas cortas y desenlaces explícitos, no ensayos.
- [Self-service scope creep] → Sólo stale list + related + mutaciones de desenlace ya modeladas.

## Migration Plan

1. Actualizar prompts/skill/hooks.
2. Añadir/ajustar self-service + tests.
3. Sin migración de datos.

## Open Questions

- ¿La UI (recallum-ui) entra en este change o sólo API? Default: API + contrato; UI sólo si ya hay pantalla obvia que consuma esos endpoints en el mismo repo.
