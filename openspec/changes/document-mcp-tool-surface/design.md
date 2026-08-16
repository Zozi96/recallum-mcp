## Context

El servidor MCP ya anuncia once herramientas; el README aún dice nueve y omite `related_memories` y `reconfirm`. El spec de integración ya es correcto; el desfase es documental y de gate.

## Goals / Non-Goals

**Goals:**
- Alinear README y guías de superficie con el conjunto canónico de once herramientas.
- Añadir un check reproducible en el gate rápido que falle si la docs diverge.

**Non-Goals:**
- Cambiar runtime MCP, esquemas, prompts o comportamiento de herramientas.
- Reescribir toda la documentación de clientes más allá de la enumeración de superficie.

## Decisions

- **Fuente de verdad**: el conjunto canónico es el del spec/MCP server (once nombres fijos), no un conteo derivado dinámicamente del proceso en CI (más frágil). El check compara docs contra esa lista allowlisted.
- **Alcance del check**: README obligatorio; `docs/clients.md` si enumera tools. Evitar escanear todo el árbol markdown.
- **Implementación del check**: script o test unitario/plugin en la lane rápida existente, sin red.

## Risks / Trade-offs

- [Falsos positivos por prosa] → Anclar el check a una lista explícita o sección marcada, no a NLP.
- [Docs fuera de árbol] → Sólo artefactos versionados del repo.

## Migration Plan

1. Actualizar README (y clients si aplica).
2. Añadir check al gate.
3. Sin migración de datos ni rollback especial.

## Open Questions

Ninguna bloqueante.
