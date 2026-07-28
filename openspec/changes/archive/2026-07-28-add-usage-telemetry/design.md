## Context

`BearerAuthMiddleware.on_call_tool` autentica cada llamada y ejecuta la herramienta dentro de `identity_scope`. Es el único punto por el que pasan todas las llamadas con una identidad ya resuelta, y por tanto el sitio natural para observarlas.

Ese mismo módulo documenta la restricción que condiciona esta change:

> How stale `last_used_at` may get before authentication refreshes it. Every refresh is a write on a row that a busy agent hits on every single tool call, so the timestamp trades exactness for not serialising the hot path.

El proyecto ya decidió una vez que la exactitud temporal vale menos que no escribir por llamada. Esta change no puede contradecir esa decisión sin justificarla.

`MemoryService.recall` degrada a búsqueda textual cuando el cliente de embeddings falla, y hoy esa degradación no deja rastro fuera de un aviso en el registro de la aplicación.

Todo el contenido de usuario vive en `memories`, con `FORCE ROW LEVEL SECURITY`. No existe todavía ninguna tabla con datos por usuario fuera de ese régimen.

## Goals / Non-Goals

**Goals:**

- Saber cómo se usa la memoria, no sólo qué contiene.
- No añadir una escritura sincrónica por llamada.
- Atribuir siempre la actividad a una identidad autenticada.
- Mantener el registro libre de contenido de usuario.
- Acotar el crecimiento del registro.
- Hacer visible la degradación por indisponibilidad de embeddings.

**Non-Goals:**

- Auditoría de seguridad o registro de accesos con garantías de no repudio.
- Trazas distribuidas, métricas de proceso o exportación a un sistema externo.
- Registrar consultas, contenidos o resultados concretos.
- Medir la calidad de la recuperación.
- Analítica en tiempo real.

## Decisions

### El volcado es diferido y por lotes, no una escritura por llamada

Tres opciones estaban sobre la mesa: escribir dentro de la misma transacción de la llamada, lanzar una tarea suelta por llamada, o acumular en memoria y volcar por lotes.

La escritura sincrónica es la más simple y la más honesta, pero añade un viaje a la base de datos a cada llamada de herramienta, contra un pool de cinco conexiones, y revierte de facto la decisión ya tomada para `last_used_at`. La tarea suelta por llamada quita la latencia pero no acota nada: una ráfaga crea tantas tareas y tantas conexiones como llamadas.

Se elige la acumulación en memoria con volcado al superar un número de eventos o un intervalo, lo que llegue antes. Es la misma moneda que el proyecto ya gastó: exactitud a cambio de no serializar. La diferencia es que aquí lo que se pierde no es precisión temporal sino durabilidad ante un corte, lo que obliga a decidir si eso es aceptable.

### Perder actividad ante un corte es aceptable; perder una memoria no

La distinción es la que justifica todo lo anterior. Una memoria es contenido irrecuperable creado por una persona. Un evento de actividad es una observación estadística, y perder unos segundos de observaciones sólo desplaza mínimamente unos agregados que se leen en gráficas.

Por eso el volcado también se ejecuta al cerrar la aplicación de forma ordenada, que cubre el caso frecuente, y no se intenta ninguna garantía para el corte abrupto, que es el caso raro y de consecuencia menor. El buffer está acotado: si el volcado no consigue avanzar, se descartan los eventos más antiguos antes que dejar crecer la memoria del proceso.

### El registro no contiene texto de usuario

Se guarda identificador de usuario, herramienta, proyecto, duración, número de resultados, si hubo degradación y el instante. No se guarda la consulta de `recall` ni el contenido de `remember`.

La tentación es real: saber qué se busca sería lo más informativo del panel. Pero el texto de una consulta es contenido del usuario, y meterlo en una tabla legible por la administración crearía una puerta lateral al contenido que RLS protege deliberadamente en `memories`. La barrera dejaría de ser una propiedad del esquema para pasar a depender de que nadie consulte la tabla equivocada.

El nombre del proyecto sí se guarda, porque ya es un dato de organización que el operador conoce y sin él el reparto por proyecto resulta inútil.

### La actividad es dato operativo y vive fuera de Row-Level Security

Esta es la consecuencia incómoda de la decisión anterior y conviene enunciarla como norma, no como excepción: **el contenido está protegido por RLS; los conteos y la telemetría son dato operativo.**

El registro queda fuera de RLS porque debe poder agregarse por la administración, que bajo `SessionProvider.admin()` no vería ninguna fila sometida a las políticas. A cambio, la norma restringe qué puede contener: si algún día se quisiera guardar texto de consultas, no bastaría con añadir una columna, habría que cambiar la tabla de régimen.

El aislamiento de las estadísticas propias de cada usuario pasa entonces a depender del filtro de la capa de aplicación. Es una barrera más débil que la de `memories`, y esa asimetría es deliberada porque lo que protege es más débil también.

### La instrumentación va después de la autenticación

Se añade una etapa de middleware posterior a `BearerAuthMiddleware`, de modo que toda actividad registrada corresponde a una identidad ya verificada y las llamadas rechazadas por credencial inválida no generan eventos.

La consecuencia aceptada es que los intentos fallidos de autenticación no quedan registrados aquí. Eso es vigilancia de seguridad, no telemetría de uso, y mezclarlas obligaría a registrar eventos sin usuario atribuible en una tabla cuyo sentido es agrupar por usuario.

### La retención se resuelve borrando, no agregando

El registro se purga por antigüedad con un plazo configurable de noventa días. No se introducen tablas de resumen ni agregados materializados.

Con el volumen esperado, unas gráficas sobre noventa días de eventos son una consulta ordinaria. Los resúmenes por periodo son la optimización natural cuando el borrado deje de bastar, y pueden añadirse después sin cambiar lo que ve quien consulta.

## Risks / Trade-offs

- **Un corte abrupto pierde la actividad no volcada.** Aceptado explícitamente: es dato estadístico, no contenido.
- **El aislamiento de la actividad por usuario depende de la aplicación, no de la base de datos.** Se compensa restringiendo por norma qué puede contener la tabla.
- **El volcado por lotes escribe en ráfagas.** Con lotes acotados es preferible a un goteo constante contra un pool pequeño.
- **La actividad se atribuye a un usuario, no a una API key concreta.** Simplifica el modelo pero impide responder "qué cliente hace esto"; se puede añadir después sin romper lo existente.
- **Instrumentar el camino de llamada añade una etapa de middleware a cada llamada.** Su coste debe ser una escritura en memoria, y así debe verificarse.

## Migration Plan

1. Migración aditiva que crea el almacenamiento de actividad. Nada existente cambia.
2. Desplegar con la instrumentación activa; el registro empieza vacío y las gráficas se llenan con el uso.
3. Verificar que la latencia de las llamadas de herramientas no cambia de forma apreciable.
4. Activar la purga periódica una vez confirmado el crecimiento real.

## Open Questions

- Umbrales concretos de tamaño de lote e intervalo de volcado frente al uso real.
- Si la purga debe ser una tarea periódica del proceso o una operación del CLI ejecutada externamente.
- Si conviene registrar también el resultado de `context`, que un agente invoca al iniciar sesión y podría dominar los conteos.
- Si el número de resultados debe registrarse en bruto o agrupado, dado que en consultas muy específicas podría insinuar el tamaño del conjunto de memorias.
