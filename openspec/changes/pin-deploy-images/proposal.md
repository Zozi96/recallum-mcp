## Why

Las referencias a imágenes de contenedor no son reproducibles: `recallum:latest` (deploy/dokploy-compose.yml:13,33), `ollama/ollama:latest` (deploy/docker-compose.yml:55 y dokploy-compose.yml:66) y `python:3.14-slim` (deploy/Dockerfile:3) se resuelven en el momento del pull, así que dos despliegues del mismo commit pueden correr código distinto. Un upstream malicioso o accidental publicado entre dos despliegues cambia el entorno en producción sin pasar por revisión.

## What Changes

- Toda imagen referenciada en despliegue (`Dockerfile`, `docker-compose.yml`, `dokploy-compose.yml`) se ancla a una versión inmutable: digest SHA256 o etiqueta versionada fija, nunca `latest` ni etiqueta móvil.
- Se documenta el procedimiento de actualización deliberada (cómo y con qué frecuencia revisar los digests) en `docs/operations.md`.
- El contrato HTTP/MCP no cambia; es un cambio puramente operativo.

## Capabilities

### New Capabilities

(ninguna — cambio puramente operativo, sin cambio de comportamiento de sistema; declarado `skip_specs` en `.openspec.yaml`)

### Modified Capabilities

(ninguna)

## Impact

- Archivos: `deploy/Dockerfile`, `deploy/docker-compose.yml`, `deploy/dokploy-compose.yml`.
- Documentación: `docs/operations.md`.
- Sin cambios en código Python ni en specs de comportamiento.
