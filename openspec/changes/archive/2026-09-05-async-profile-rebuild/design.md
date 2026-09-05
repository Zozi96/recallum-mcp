## Context

Estado actual (verificado):

- Toda mutación de memoria invoca `_rebuild_profiles_for_memory` tras el commit: `remember` (`service.py:212`), `reconfirm` (`service.py:1486`), `update`, `merge_memories` y `forget` siguen el mismo patrón. El método lista las claves de perfil afectadas (la clave global y, para memorias globales, todos los proyectos del usuario vía `list_profile_projects`) y delega en `_rebuild_profiles_for_keys` (`service.py:1610-1620`), que recorre las memorias activas y hace un upsert CAS con reintentos.
- La lectura ya tolera un perfil obsoleto: `get_profile` compara la generación materializada con la del corpus y, si difiere, reconstruye el slice static en el momento (`memory-profile`, `Reconstrucción perezosa al leer` y `Dynamic ensamblado en lectura`). `_rebuild_profiles_for_keys` es best-effort: su fallo se registra y no invalida la mutación (spec `Fallo de rebuild no revierte el remember`, y `service.py:1617-1619` traga el fallo de `list_profile_projects`).
- El ciclo de vida del proceso ya aloja un trabajador con ese patrón: `TelemetryBuffer` arranca/para en `app.py` y encola trabajo sin E/S por llamada (`telemetry/buffer.py:18-64`).

## Goals / Non-Goals

**Goals:**

- Sacar el coste O(corpus) de la latencia de escritura: la mutación sólo incrementa la generación y devuelve.
- Mantener la garantía de lectura: ninguna respuesta de perfil es más vieja que la última mutación confirmada.
- Reutilizar el patrón de ciclo de vida ya existente (trabajador con arranque/parada en `app.py`) sin nuevos subsistemas.

**Non-Goals:**

- No se cambia la forma del perfil materializado, el contenido del slice static/dynamic ni el cómputo del hash (`memory/profile_select.py` intacto).
- No se introduce una cola persistente ni un planificador distribuido: un solo proceso, `workers=1` en despliegue (`deploy/entrypoint.sh`), lo permite.
- No se altera la semántica de la generación ni las reglas de cuándo incrementa.

## Decisions

1. **Señal existente, no nueva infraestructura.** La generación del usuario ya marca las claves pendientes; el cambio consiste en dejar de consumir esa señal en línea. Las mutaciones dejan de invocar `_rebuild_profiles_for_memory` y, en su lugar, registran la clave afectada en una cola en memoria acotada (mismo patrón que `TelemetryBuffer`); un trabajador del proceso las drena en lotes. Alternativa considerada: no añadir trabajador y depender sólo de la lectura perezosa — rechazada, porque una caída prolongada de lecturas dejaría las claves sin reponer indefinidamente y la primera lectura pagaría el coste O(corpus) completo con mal factor sorpresa.

2. **La lectura perezosa sigue siendo la red de seguridad.** Si la lectura llega antes que el trabajador (caso dominante en uso activo), la comparación de generación dispara la reconstrucción en el momento — comportamiento ya especificado en `Reconstrucción perezosa al leer`. Así el trabajador es una optimización de calentamiento, no una condición de corrección, y el sistema sigue funcionando si el trabajador muere.

3. **Cola en memoria, no persistente.** El materializado se reconstruye desde el estado de la base en cualquier momento; perder la cola en un reinicio sólo difiere trabajo que la lectura perezosa o el siguiente arranque repondrán. Una tabla de trabajos añadiría migración y limpieza sin ganar corrección. Trade-off asumido: tras un reinicio con cola llena, algunas claves se reponen en la primera lectura en lugar de en segundo plano.

4. **Coalescer por clave.** La cola guarda claves de perfil (usuario, proyecto|global), no mutaciones: N mutaciones seguidas sobre la misma clave producen una única reconstrucción pendiente. Esto amortigua ráfagas de escritura (p.ej. `remember_batch`) sobre el mismo perfil.

## Risks / Trade-offs

- **Ventana de obsolescencia perceptible**: un lector que consulte la fila materializada directamente (sin pasar por la lectura perezosa del servicio) puede ver un perfil viejo hasta que el trabajador lo repone. Hoy no hay tal lector en el repo; se documenta en el ADR si aparece.
- **Doble reconstrucción**: trabajador y lectura perezosa pueden coincidir sobre la misma clave. El upsert CAS existente ya ordena el conflicto (perdedor reintenta o descarta); se acepta el trabajo duplicado ocasional a cambio de no introducir bloqueos.
- **Acoplamiento al patrón de un solo trabajador**: con `workers=1` en despliegue no hay competencia entre procesos; si algún día se escala horizontalmente, la cola en memoria ya no basta y habrá que mover la señal a la base. Queda fuera de alcance.
