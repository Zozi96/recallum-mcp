## Context

La skill `recallum-memory` ya define la clave conceptual de recuperación, los disparadores semánticos, `limit=3` y la supresión de consultas redundantes. El hook compartido por Codex, Claude Code y Grok Build inyecta instrucciones distintas según exista un digest, no existan memorias o falle la carga; esas variantes hacen explícitos el inicio y el cierre, pero no presentan de forma uniforme el checkpoint intermedio.

El evaluador actual ya valida escenarios y trazas acotadas y calcula recuperación crítica, aplicación, llamadas innecesarias, repetición y caracteres servidos. Sus seis ejecuciones versionadas son fixtures manuales para dos políticas sobre tres escenarios. La telemetría de producción es deliberadamente content-free y no puede determinar si una llamada era aplicable ni si el agente utilizó el resultado.

## Goals / Non-Goals

**Goals:**

- Hacer visible el ciclo inicio-pivote-cierre sin duplicar la skill completa en cada sesión.
- Obtener trazas de llamadas realizadas por procesos reales de agentes contra tareas sintéticas reproducibles.
- Verificar aplicación mediante estado observable del workspace, sin juez LLM ni autodeclaración del agente.
- Comparar varias ejecuciones por cliente y política sin mezclar fixtures con evidencia observada.

**Non-Goals:**

- Cambiar el servidor Recallum, sus herramientas, ranking, persistencia o telemetría.
- Instalar clientes, administrar cuentas o credenciales comerciales, o iniciar ejecuciones pagadas sin una orden explícita del operador.
- Parsear transcriptos propietarios de Codex, Claude Code o Grok Build.
- Convertir el benchmark sintético en una medida de calidad general del modelo o del ranking de memoria.

## Decisions

### 1. `SessionStart` reutiliza un único sufijo breve de checkpoint

`_session_context` construirá una sola vez un sufijo que nombra `recall` mediante `_tool`, describe el cambio material de subsistema, hipótesis o decisión, exige consulta inglesa del delta con proyecto y `limit=3`, y ordena omitir la llamada cuando el contexto ya cubre la decisión. Las tres ramas existentes añadirán el mismo sufijo antes de la guía de captura final.

La skill permanece como fuente completa de matices. El hook sólo conserva el recordatorio mínimo que debe sobrevivir aunque la skill se cargue tarde.

Alternativas descartadas:

- Añadir otro hook por herramienta o por tiempo: aumenta ruido sin observar la transición semántica.
- Copiar toda la política en `SessionStart`: consume contexto y crea dos documentos que pueden divergir.
- Crear una herramienta MCP `checkpoint`: las operaciones `context` y `recall` ya cubren el comportamiento.

### 2. El benchmark usa un probe MCP local y un comando de agente suministrado por el operador

Un runner opt-in recibirá escenario, cliente, política, repeticiones y un comando después de `--`. Para cada ejecución creará un workspace temporal, iniciará en loopback un probe MCP con token efímero y expondrá al comando mediante variables de entorno la URL, token, ruta del workspace, prompt sintético y clave de proyecto. Ejecutará el comando como una lista de argumentos sin interpolación de shell y no incorporará `stdout` ni `stderr` a la traza. La documentación dará ejemplos de configuración aislada para cada cliente; el runner no modificará instalaciones ni configuración persistente.

El probe implementará sólo las operaciones necesarias para el flujo evaluado y devolverá respuestas deterministas a partir del escenario. Registrará las llamadas directamente en el servidor de prueba, evitando depender de formatos de transcriptos. El runner impondrá timeout y terminará el probe aunque el agente falle.

Alternativas descartadas:

- Telemetría de producción: no conoce el pivote ni la aplicación y ampliarla introduciría riesgos de privacidad.
- Transcriptos de cliente: son inestables, distintos por proveedor y pueden contener razonamiento o datos sensibles.
- Más fixtures manuales: prueban el evaluador, no la adherencia del agente.

### 3. Los escenarios observados separan tarea, corpus y checks objetivos

Cada escenario observado reutilizará el id y las claves del dataset de flujo, pero mantendrá sus artefactos ejecutables fuera del JSON de trazas: un prompt sintético, un fixture mínimo de repositorio, reglas deterministas para clasificar consultas y devolver claves, y verificadores acotados que asignan criterios según el estado observable del workspace.

El probe puede inspeccionar en memoria una consulta sintética para reconocer los identificadores del pivote. Sólo persiste la fase asignada, la herramienta, las claves retornadas y los caracteres servidos. Al finalizar, el runner ejecuta los checks en el workspace y añade un evento de decisión con los criterios satisfechos; el agente nunca reporta esos criterios.

Alternativas descartadas:

- Juez LLM sobre la respuesta final: añade coste, variabilidad y otra fuente de credenciales.
- Pedir al agente un JSON de autoevaluación: mide obediencia al formato, no aplicación real.

### 4. El formato de ejecuciones se amplía de forma compatible

Las ejecuciones admitirán metadatos opcionales `source`, `client`, `client_version` y estado de finalización. La ausencia de esos campos conservará el significado del dataset vigente como fixture. `run_id` seguirá siendo obligatorio para repeticiones y único en el archivo.

La unicidad dejará de prohibir varias ejecuciones por política y escenario. La comparación agrupará por procedencia, cliente y política; informará cobertura, incompletas, tasas binarias y promedios de llamadas, duplicación y caracteres. Los fixtures actuales seguirán produciendo el mismo informe cuando se evalúen solos.

Alternativas descartadas:

- Codificar cliente y repetición dentro de `policy`: evita cambios de esquema, pero impide agrupación fiable y mezcla conceptos distintos.
- Reemplazar los fixtures actuales: se necesitan como prueba determinista del cálculo de métricas.

### 5. Las ejecuciones reales son explícitas y las pruebas automatizadas usan un agente falso

El runner no invocará ningún cliente por defecto. Las pruebas usarán un proceso falso que llama al probe y modifica el fixture, suficiente para validar captura, timeout, limpieza, checks y conversión de trazas sin red ni coste externo. Las ejecuciones de Codex, Claude Code y Grok Build serán un paso manual y opt-in documentado; se recomienda repetir cada escenario tres veces antes de comparar políticas.

## Risks / Trade-offs

- [El probe no reproduce todo el ranking o latencia de producción] → Limitar su objetivo a la decisión de llamar y aplicar; mantener separada la evaluación de ranking existente.
- [La configuración temporal difiere entre clientes] → Usar un contrato común de variables de entorno y ejemplos aislados, sin adaptadores que muten la configuración del usuario.
- [Un escenario sintético puede favorecer una redacción concreta] → Reutilizar varios pivotes y controles negativos y reportar cada cliente por separado.
- [El probe observa consultas completas durante la ejecución] → Aceptar sólo tareas sintéticas, procesar consultas en memoria y persistir únicamente clasificaciones y claves.
- [Las repeticiones aumentan coste y tiempo] → Mantener una ejecución por defecto y hacer configurable la recomendación de tres.
- [La guía breve puede aumentar llamadas] → Comparar corrección junto con llamadas innecesarias, repetición y caracteres; no considerar volumen como éxito.

## Migration Plan

1. Añadir el sufijo común de checkpoint y fijarlo con pruebas para las variantes de digest y los tres clientes.
2. Ampliar de forma compatible el esquema y el agregador del evaluador, conservando el informe actual para fixtures existentes.
3. Incorporar el probe, runner, fixtures sintéticos y agente falso con pruebas de captura, verificación, timeout y limpieza.
4. Documentar comandos opt-in y capturar una matriz observada por cliente y política cuando cada cliente esté disponible.
5. Ajustar sólo la redacción breve si las ejecuciones muestran omisiones o redundancia; cambios de API o telemetría requieren otra propuesta.

El rollback elimina el sufijo nuevo del hook y conserva el benchmark como herramienta offline. No hay migraciones de datos ni cambios desplegados del servidor.
