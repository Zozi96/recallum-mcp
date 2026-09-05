## 1. Pineado de imágenes

- [x] 1.1 Anclar la imagen base de `deploy/Dockerfile` a un digest SHA256 con comentario de la etiqueta que resuelve. Verificación: `grep '^FROM' deploy/Dockerfile` muestra digest, y build local reproducible.
- [x] 1.2 Anclar `pgvector/pgvector` y `ollama/ollama` en `deploy/docker-compose.yml` a digest. Verificación: `grep image: deploy/docker-compose.yml` no muestra `:latest` ni etiqueta móvil.
- [x] 1.3 Anclar o versionar explícitamente `recallum` en `deploy/dokploy-compose.yml`, eliminando `:latest`. Verificación: `grep image: deploy/dokploy-compose.yml` sin `:latest`.

## 2. Documentación del procedimiento

- [x] 2.1 Añadir a `docs/operations.md` la política de actualización de digests (cómo comprobarlos y con qué cadencia). Verificación: el documento existe y menciona cada imagen pineada.

## 3. Validación

- [x] 3.1 Levantar el compose de desarrollo y confirmar que los servicios arrancan con las imágenes pineadas. Verificación: `docker compose up -d` (o `config`) sin errores de pull por digest inexistente.
