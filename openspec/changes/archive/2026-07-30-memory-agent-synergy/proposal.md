# Memory Agent Synergy

## Why

Los agentes que consumen Recallum reciben hoy un contexto estático y poco observable: el snapshot
inicial ignora la tarea en curso, la memoria no acumula señal de uso ni de reconfirmación, los
casi-duplicados entre categorías son invisibles para el aviso `similar`, y el bootstrap de sesión
depende de que el modelo obedezca una instrucción sin garantía ni visibilidad de fallo. Esto limita
la precisión del agente exactamente donde la herramienta debería aumentarla.

## What Changes

- `context` acepta un `focus` opcional: el snapshot incorpora memorias relevantes a la tarea usando
  el retrieval híbrido existente, sin desplazar preferencias ni constraints.
- `context` informa cuántas memorias quedaron fuera del presupuesto (`total_available`, `omitted`)
  y trunca ítems largos con marca explícita en lugar de omitirlos en silencio.
- Registro de uso por memoria (`recall_count`, `last_recalled_at`) al servirla en `recall` y
  `context`; votante opcional de uso en la fusión RRF, apagado por defecto.
- Reconfirmación con huella: re-almacenar contenido idéntico actualiza `reconfirmed_at`, visible en
  todas las respuestas para que el agente distinga hechos frescos de hechos viejos.
- El aviso `similar` de `remember` deja de filtrar por categoría: un casi-duplicado guardado como
  `fact` frente a una `decision` existente ahora se reporta.
- Nueva herramienta MCP `remember_batch`: captura por lotes acotada con resultado por ítem y éxito
  parcial, para abaratar el escaneo de captura al cierre de sesión.
- Autoservicio web: reasignación masiva de la clave de proyecto (migración `from_project` →
  `to_project`) con reporte de colisiones de contenido.
- Hook de sesión del plugin: obtención opt-in del digest de contexto (variables
  `RECALLUM_MCP_URL` + `RECALLUM_API_KEY`) con fail-open, derivación de clave de proyecto con
  cualquier remote cuando falta `origin`, y visibilidad explícita cuando las herramientas MCP no
  están disponibles.
- SKILL.md: reglas de delegación a subagentes (el lead pasa la clave canónica y las memorias
  relevantes; los workers no escriben), uso de `focus` y `remember_batch`, e interpretación de los
  campos de frescura y uso.

## Capabilities

### New Capabilities

- `agent-session-bootstrap`: comportamiento del plugin al iniciar o reanudar sesión — derivación
  robusta de la clave canónica de proyecto, inyección de hints y del digest de contexto, visibilidad
  de la indisponibilidad del MCP y guía de delegación a subagentes.

### Modified Capabilities

- `agent-memory-retrieval`: el contexto compacto se vuelve sensible a la tarea (`focus`), informa
  presupuesto omitido y trunca con marca; servir una memoria registra su uso.
- `agent-memory-lifecycle`: la deduplicación exacta deja huella de reconfirmación; el aviso de
  similares cruza categorías; se añade la captura por lotes.
- `mcp-agent-integration`: la superficie de herramientas pasa a siete (`remember`, `remember_batch`,
  `recall`, `context`, `list_memories`, `update`, `forget`) — el spec vigente lista cinco y omite
  `update`, que ya existe; `context` gana el parámetro `focus`.
- `web-self-service-api`: nueva reasignación de proyecto; el aviso de similares en creación cruza
  categorías; los payloads de memoria incluyen los campos de frescura y uso.

## Impact

- **DB**: migración `0008` con tres columnas nuevas en `memories` (`reconfirmed_at`,
  `last_recalled_at`, `recall_count`). Sin backfill: NULL/0 significan "sin dato".
- **Código**: `recallum/memory/service.py`, `recallum/memory/context.py`, `recallum/memory/schemas.py`,
  `recallum/memory/limits.py`, `recallum/db/repositories/memory_repo.py`, `recallum/db/models.py`,
  `recallum/mcp/server.py`, `recallum/web/self_service.py`,
  `plugins/recallum-memory/hooks/recallum_hook.py`, `plugins/recallum-memory/skills/recallum-memory/SKILL.md`.
- **Contrato**: regenerar el artefacto OpenAPI del autoservicio web.
- **Tests**: unit, contract, integración y tests del plugin (nuevo stub HTTP para el digest).
- **Compatibilidad**: cambios aditivos; ningún campo existente cambia de significado. La lista de
  herramientas pineada en tests pasa de seis a siete. El votante de uso en RRF nace con peso 0.0
  (sin efecto) hasta calibrarlo.
