## 1. Generation y uso

- [x] 1.1 Quitar `_increment_generation` de `mark_recalled` (repo real y fake) y verificar que un contrato/integración demuestra generation intacta tras recall y `recall_count` / `last_recalled_at` sí actualizados
- [x] 1.2 Verificar que create, reconfirm, update/supersede, merge, forget y reassign siguen incrementando generation (tests de perfil/CAS existentes en verde)

## 2. Dynamic en lectura

- [x] 2.1 Hacer que rebuild persista `dynamic_items=[]` y hash/ids del static, y que `get_profile` / armado del bloque servido ensamble dynamic live con las reglas de `profile_select`; verificar `test_recent_low_importance_dynamic_survives_candidate_cap` y el overflow static→dynamic sin depender de generation sucia
- [x] 2.2 Calcular el digest servido sobre static+dynamic devueltos y dejar `built_at` como el de la fila; verificar el escenario de hash servido (unitario de `profile_select` o servicio)

## 3. Snapshot de context

- [x] 3.1 Añadir lectura de snapshot en una sola sesión `for_user` (perfil+generation, tops, count, dynamic, y `search_candidates` si hay foco) y verificar con un test de repositorio/contrato que esas piezas salen de una transacción (mismo conjunto visible; fake o probe de sesión)
- [x] 3.2 Reescribir `MemoryService.context` para embed de foco (si aplica) → rebuild static sólo si mismatch → un `context_snapshot` → assemble → `mark_seen` fail-open; verificar tests de `context` (perfil no desalojado, foco degradado, omitted, sin duplicar ids)
- [x] 3.3 Verificar que `context` tras `recall` sin mutación reusa static (`built_at` estable) e incluye la memoria recién recuperada en dynamic cuando cabe

## 4. Superficies de lectura

- [x] 4.1 Alinear recurso MCP y GET self-service de perfil con el mismo ensamblado live que `get_profile`; verificar tests de perfil MCP/HTTP que cubren static+dynamic

## 5. Cierre

- [x] 5.1 Correr unit + integración de memoria/perfil/context (`tests/unit/test_memory_profile.py`, `tests/unit/test_service.py`, `tests/unit/test_context_budget.py`, `tests/integration/test_db.py` relevantes) y dejarlos en verde
