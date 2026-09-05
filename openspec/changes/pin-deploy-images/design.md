## Context

Estado actual (verificado): `deploy/Dockerfile:3` usa `FROM python:3.14-slim`; `deploy/docker-compose.yml:33` usa `pgvector/pgvector:pg17` (etiqueta versionada pero potencialmente móvil a nivel de digest) y `:55` usa `ollama/ollama:latest`; `deploy/dokploy-compose.yml:13,33` referencian `recallum:latest` y `:45`,`:66` repiten `pgvector:pg17` y `ollama:latest`.

## Goals / Non-Goals

**Goals:**

- Que un despliegue del mismo commit produzca exactamente las mismas imágenes.
- Que actualizar una imagen sea una decisión explícita y revisable.

**Non-Goals:**

- No se automatiza el bump de versiones (sin Dependabot/Renovate salvo decisión posterior).
- No se cambia la estructura del Dockerfile ni el pipeline de build.

## Decisions

1. **Digest SHA256 como ancla.** Se prefiere digest sobre etiqueta versionada donde el registry lo soporte de forma fiable, porque la etiqueta `pg17` puede recibir nuevos builds con el mismo tag. Cuando el digest no sea práctico (p.ej. imagen construida localmente, `recallum`), se fija una etiqueta versionada explícita y se elimina `:latest`.
2. **Procedimiento de actualización documentado.** En `docs/operations.md` se describe cómo comprobar el digest actual de cada imagen y con qué cadencia revisarlo, para que el pin no se convierta en obsolescencia silenciosa.

## Risks / Trade-offs

- **Mantenimiento**: los digests no se actualizan solos; un pin viejo puede acumular parches de seguridad no aplicados. Mitigación: el procedimiento documentado y, si se decide, una automatización futura.
- **Legibilidad**: los digests son opacos. Mitigación: comentario junto a cada imagen con la etiqueta que resuelve ese digest.
