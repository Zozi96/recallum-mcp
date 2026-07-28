## 1. Almacenamiento

- [x] 1.1 Añadir migración Alembic que cree la tabla de actividad con usuario, herramienta, proyecto, duración, número de resultados, marca de degradación, marca de fallo e instante.
- [x] 1.2 Añadir el índice que sirva las consultas por usuario y rango temporal.
- [x] 1.3 Dejar la tabla fuera de Row-Level Security de forma deliberada y documentar en la migración por qué, junto con la restricción de no almacenar contenido.
- [x] 1.4 Actualizar los modelos declarativos de SQLAlchemy.
- [x] 1.5 Añadir la configuración validada de tamaño de lote, intervalo de volcado, límite del buffer y plazo de retención.

## 2. Acumulación y volcado

- [x] 2.1 Implementar el acumulador en memoria con límite superior y descarte de lo más antiguo al alcanzarlo.
- [x] 2.2 Implementar el volcado agrupado en una sola escritura por lote.
- [x] 2.3 Disparar el volcado al superar el tamaño de lote o al cumplirse el intervalo, lo que ocurra antes.
- [x] 2.4 Ligar la tarea de volcado periódico al ciclo de vida de la aplicación y forzar un volcado final en el cierre ordenado.
- [x] 2.5 Aislar los fallos de volcado para que nunca afecten a las llamadas de herramientas.
- [x] 2.6 Añadir pruebas unitarias con reloj controlado para disparo por tamaño, disparo por intervalo, descarte por límite y volcado en el cierre.

## 3. Instrumentación

- [x] 3.1 Implementar la etapa de middleware de FastMCP que mide la llamada y entrega el evento al acumulador.
- [x] 3.2 Encadenarla después de la autenticación, de modo que toda actividad tenga identidad verificada.
- [x] 3.3 Registrar también las llamadas que terminan en error, distinguiéndolas de las correctas.
- [x] 3.4 Propagar desde la recuperación la indicación de que se sirvió degradada, sin cambiar la respuesta que reciben los agentes.
- [x] 3.5 Extraer el proyecto de la llamada cuando exista, sin incorporar ningún otro argumento.
- [x] 3.6 Añadir prueba de que una llamada rechazada por credencial no genera actividad.
- [x] 3.7 Añadir prueba de que la etapa de instrumentación no realiza operaciones de base de datos.

## 4. Consulta de actividad

- [x] 4.1 Implementar el repositorio de agregados por usuario y rango temporal.
- [x] 4.2 Implementar el reparto por herramienta, el reparto por proyecto y la frecuencia de degradación.
- [x] 4.3 Exponer la actividad propia en la API de autoservicio.
- [x] 4.4 Filtrar por usuario en la capa de aplicación y añadir prueba de aislamiento entre dos usuarios.
- [x] 4.5 Añadir prueba del caso sin actividad registrada.

## 5. Retención

- [x] 5.1 Implementar la purga por antigüedad según el plazo configurado.
- [x] 5.2 Ejecutarla periódicamente sin bloquear las llamadas de herramientas.
- [x] 5.3 Añadir prueba de integración que confirme que se elimina lo antiguo y se conserva lo reciente.

## 6. Verificación y documentación

- [x] 6.1 Añadir prueba que confirme que ninguna columna del registro contiene consultas ni contenido de memorias.
- [x] 6.2 Comprobar que las herramientas MCP mantienen argumentos, respuestas y comportamiento sin cambios.
- [x] 6.3 Medir el efecto de la instrumentación sobre la latencia de una llamada de herramienta.
- [x] 6.4 Documentar la configuración nueva en el runbook de operaciones.
- [x] 6.5 Registrar en `CONTEXT.md` la norma de que el contenido queda protegido por RLS mientras la telemetría es dato operativo, y qué implica para lo que puede almacenarse.
