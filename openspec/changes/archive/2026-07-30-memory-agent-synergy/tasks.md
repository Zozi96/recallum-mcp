# Tasks — memory-agent-synergy

## 1. Esquema y modelo

- [x] 1.1 Migración Alembic `0008_agent_synergy`: columnas `reconfirmed_at timestamptz NULL`, `last_recalled_at timestamptz NULL`, `recall_count integer NOT NULL DEFAULT 0` en `memories`, con downgrade
- [x] 1.2 Actualizar ORM `Memory` en `recallum/db/models.py` con las tres columnas

## 2. Repositorio

- [x] 2.1 `similar_active`: eliminar el parámetro y filtro `category` (docstring incluido) y ajustar `_similar_to`
- [x] 2.2 Nuevo `mark_reconfirmed(user_id, memory_id)`: UPDATE de `reconfirmed_at = now()`
- [x] 2.3 Nuevo `mark_recalled(user_id, ids)`: UPDATE único de `recall_count + 1` y `last_recalled_at = now()`
- [x] 2.4 Nuevo `count_active_visible(user_id, visibility)` para `total_available`
- [x] 2.5 Nuevo `reassign_project(user_id, from_project, to_project)`: mueve activos sin colisión de `content_hash` en destino y devuelve movidos + ids en colisión
- [x] 2.6 Actualizar contrato en `tests/contract/memory_repository.py` (similar cross-categoría, marcas de uso/reconfirmación, reasignación)

## 3. Dominio: servicio, presupuesto y schemas

- [x] 3.1 `limits.py`: `context_focus_limit=10`, `context_truncate_floor=200`, `batch_max_items=10`, `recall_usage_weight=0.0` (validado 0.0–1.0)
- [x] 3.2 `schemas.py`: `reconfirmed_at`, `last_recalled_at`, `recall_count` en `MemoryOut`/`ContextItem`/`SimilarMemory`; `content_truncated` en `ContextItem`; `total_available`, `omitted` y `focus` en `ContextResult`; schemas de lote (`BatchItem`, `BatchItemResult`, `BatchResult`)
- [x] 3.3 `remember`: marcar reconfirmación en la rama de dedup y en la rama de carrera por `IntegrityError`
- [x] 3.4 `remember_batch` en el servicio: validación de tamaño de lote, iteración con captura de errores por ítem, éxito parcial
- [x] 3.5 `context`: parámetro `focus` con recuperación híbrida degradable, merge deduplicado en los pools, `total_available`/`omitted` exactos
- [x] 3.6 `SessionContextBudget.assemble`: truncado con elipsis y `content_truncated=True` cuando el resto de presupuesto ≥ floor; `break` en lugar de `continue` al agotar caracteres
- [x] 3.7 Registro de uso: `mark_recalled` tras armar resultados de `recall` y `context`, envuelto en try/except con warning
- [x] 3.8 Votante de uso en `_reciprocal_rank_fusion` por `recall_count` (ranking de competencia) gobernado por `recall_usage_weight`

## 4. Superficie MCP

- [x] 4.1 `context`: exponer `focus` y actualizar descripción (usar `recall` cuando `omitted > 0`)
- [x] 4.2 Nueva tool `remember_batch` con esquema validado y docstring de uso para captura de cierre
- [x] 4.3 Actualizar `INSTRUCTIONS` del servidor (batch, focus, frescura/uso, similares cross-categoría)
- [x] 4.4 Actualizar tests de herramientas pineadas (`tests/unit/test_mcp_tools.py`): siete tools y esquemas sin inputs prohibidos

## 5. Autoservicio web

- [x] 5.1 Endpoint de reasignación de proyecto (sesión web, validación de claves, respuesta movidos + colisiones)
- [x] 5.2 Regenerar el contrato OpenAPI (`scripts/export_web_openapi.py`) y verificar el test de divergencia

## 6. Plugin: hook y skill

- [x] 6.1 Hook: fallback de clave de proyecto a cualquier remote cuando falta `origin`
- [x] 6.2 Hook: digest opt-in vía `RECALLUM_MCP_URL`+`RECALLUM_API_KEY` (initialize → initialized → tools/call `context`, urllib, JSON+SSE, `mcp-session-id`, presupuesto ~2.5 s, fail-open total)
- [x] 6.3 Hook: hint de sesión pide comunicar una única vez la indisponibilidad de tools tras buscarlas
- [x] 6.4 SKILL.md: sección de delegación (lead pasa clave y memorias; workers no escriben), uso de `focus` y `remember_batch`, interpretación de `reconfirmed_at`/`last_recalled_at`/`recall_count`
- [x] 6.5 Skill de setup: documentar las variables opcionales del digest
- [x] 6.6 Tests del plugin: stub HTTP local para el digest (éxito, timeout, 401, respuesta corrupta → fail-open), fallback de remote, texto del hint

## 7. Validación

- [x] 7.1 Tests unitarios nuevos/ajustados: servicio (focus, batch, reconfirmación, uso), presupuesto (truncado y transparencia), fusión (votante de uso con peso 0 y no-0)
- [x] 7.2 Tests de integración DB: migración, `mark_*`, reasignación con colisiones, similar cross-categoría
- [x] 7.3 Suite completa (`pytest`) + `openspec validate --strict` en verde
