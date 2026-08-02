## Context

El plugin actual cubre tres momentos: `SessionStart` deriva la clave canónica e intenta inyectar un digest compacto, `UserPromptSubmit` recuerda usar Recallum cuando el usuario menciona explícitamente memoria y la skill prescribe una captura al finalizar. Los hooks reciben eventos del cliente, pero no observan los cambios internos de hipótesis o superficie que ocurren mientras el agente investiga.

`context(focus=...)` y `recall` ya ofrecen toda la recuperación necesaria. El primero combina memorias importantes con hasta diez coincidencias del foco; el segundo permite consultas precisas y un límite explícito. La telemetría evita deliberadamente consultas y contenido, y la evaluación existente mide MRR y recall@k del ranking, no la decisión del agente de consultar ni el uso posterior del resultado.

## Goals / Non-Goals

**Goals:**

- Hacer que el agente recupere memoria justo cuando cambia materialmente la parte de la tarea que determina relevancia.
- Mantener bajo y predecible el coste de cada checkpoint.
- Evitar llamadas periódicas, repetidas o motivadas sólo por actividad mecánica.
- Validar separadamente que el agente consulta a tiempo, recibe la memoria crítica y la aplica.
- Mantener la política uniforme para Codex, Claude Code y Grok Build.

**Non-Goals:**

- Cambiar firmas MCP, persistencia, ranking o valores de `MemoryLimits`.
- Inferir transiciones semánticas en el servidor o almacenar consultas, razonamiento o contenido en telemetría.
- Añadir hooks que disparen recuperación después de cada herramienta.
- Activar `recall_usage_weight` o usar frecuencia histórica como señal de utilidad.
- Garantizar deduplicación de resultados entre llamadas desde el servidor.

## Decisions

### 1. La transición se modela como cambio de clave de recuperación

La skill describirá la clave conceptual como `project + active objective + current subsystem/hypothesis/decision`. El agente ejecutará un checkpoint sólo cuando esa clave cambie de forma material y sea plausible que una memoria durable altere la siguiente acción.

Esto concentra el criterio en relevancia, no en hitos artificiales. Entre los disparadores positivos estarán un subsistema nuevo, una hipótesis causal reemplazada y una decisión sensible con posible historial. El tiempo transcurrido, el número de herramientas, un fallo aislado y una compactación con digest suficiente serán disparadores negativos explícitos.

Alternativas descartadas:

- Intervalos temporales o cada N herramientas: son fáciles de instrumentar pero no correlacionan con cambios de relevancia.
- Inferencia desde telemetría: los eventos no contienen contexto semántico por diseño.
- `PostToolUse`: multiplicaría recordatorios y seguiría sin conocer la intención del agente.

### 2. Los checkpoints usan `recall`, no snapshots repetidos

El contexto de inicio conserva preferencias, restricciones y memorias importantes. Durante la tarea, `recall` consultará sólo el delta semántico con `project`, consulta inglesa e identificadores verbatim. `context(focus=...)` quedará reservado para inicio, reanudación o reconstrucción de un snapshot cuando un digest posterior a compactación no cubra el foco activo.

Cada checkpoint utilizará `limit=3`. Es un presupuesto del agente, no un cambio al default del servidor. La exploración mostró que ampliar una consulta enfocada a cinco añadió resultados laterales; tres conserva el núcleo útil y permite revisar cada resultado.

Alternativas descartadas:

- Cambiar `recall_default_limit` globalmente: afectaría consumidores ajenos al flujo del plugin.
- Llamar siempre `context` con un foco nuevo: reinyecta la parte importante del snapshot y aumenta duplicación y tokens.
- Añadir `exclude_ids` ahora: amplía el API sin demostrar todavía que la deduplicación cliente sea insuficiente.

### 3. La supresión de duplicados es estado efímero del agente

La skill exigirá recordar dentro del contexto activo las claves ya consultadas y los ids ya servidos. Una consulta equivalente no se repite sin nueva evidencia; un resultado ya conocido puede reconocerse y no necesita volver a analizarse. Este estado no se persiste como memoria durable.

Tras una compactación, el agente usa el digest inyectado como base. Sólo reconstruye un foco cuando el digest no contiene lo necesario para la tarea activa. No se añadirá estado de sesión al servidor.

### 4. La evaluación de flujo queda separada de la evaluación de ranking

Se añadirá un dataset versionado de escenarios. Cada escenario contendrá un corpus de memorias identificadas por claves, contexto inicial, fases de tarea, un pivote opcional, memorias críticas, condiciones esperadas de checkpoint y criterios observables de aplicación correcta.

Un evaluador sin dependencia de un proveedor LLM puntuará registros JSON de ejecuciones producidos por una sesión controlada o un harness externo. Cada registro contendrá eventos acotados: fase, herramienta, ids o claves retornadas, caracteres servidos y criterios de resultado satisfechos. No contendrá razonamiento interno, credenciales ni contenido completo de usuario.

El informe separará:

- tasa de recuperación crítica antes de la decisión;
- aplicación correcta de la memoria crítica;
- checkpoints innecesarios;
- exposiciones repetidas;
- llamadas y caracteres servidos.

La infraestructura existente de ranking continuará midiendo si una consulta conocida devuelve la memoria esperada. La nueva evaluación medirá si el agente eligió consultar y utilizó el resultado; ninguna sustituye a la otra.

### 5. La primera entrega no añade telemetría de checkpoints

Agregar un parámetro `trigger` o una columna de actividad sólo permitiría contar tipos declarados por el agente; no demostraría utilidad. Primero se validará la política con escenarios controlados. Una propuesta posterior podrá añadir un enum sin contenido si los resultados muestran que hace falta observar adopción real.

## Risks / Trade-offs

- [El concepto de cambio “material” puede interpretarse de forma distinta entre agentes] → Incluir ejemplos positivos y negativos contractuales en la skill y sus pruebas.
- [Tres resultados pueden omitir una memoria crítica] → Medirlo en el dataset; ampliar el límite sólo con evidencia y sin cambiar el default global de forma prematura.
- [El estado efímero de consultas se pierde tras compactar] → Usar el digest como base y permitir una única recuperación enfocada cuando falte el foco activo.
- [Las pruebas de texto pueden asegurar la guía pero no su cumplimiento por modelos] → Mantener una evaluación de flujo separada con ejecuciones comparables y criterios observables.
- [Los registros de evaluación podrían capturar información sensible] → Versionar sólo escenarios sintéticos; para ejecuciones reales conservar claves e indicadores, nunca prompts, razonamiento o contenido completo.
- [La política puede aumentar latencia y tokens] → Reportar llamadas, caracteres y duplicación junto con corrección; no considerar el aumento de llamadas como éxito.

## Migration Plan

1. Añadir escenarios y el evaluador de flujo con fixtures sintéticos y pruebas del cálculo de métricas.
2. Capturar una línea base usando la guía vigente.
3. Actualizar la skill y sus pruebas contractuales para incorporar la política.
4. Ejecutar los mismos escenarios con checkpoints y comparar corrección y coste.
5. Publicar la actualización del plugin sólo si la comparación no muestra una regresión material.

El rollback consiste en restaurar el texto anterior de la skill; no existen migraciones de datos ni cambios de API. Los fixtures y reportes pueden conservarse para futuras iteraciones.

## Open Questions

- Qué conjunto mínimo de escenarios representa bien diagnóstico, implementación, seguridad, compatibilidad y despliegue sin adaptar la política a un único tipo de tarea.
- Qué umbrales de mejora y coste deben bloquear la publicación; se definirán después de obtener la línea base, no como números arbitrarios en esta propuesta.
- Qué formato de exportación de trazas resulta práctico en cada cliente sin introducir acoplamiento específico en la primera entrega.
