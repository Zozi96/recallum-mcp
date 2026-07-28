## Context

`MemoryService` no sabe nada de MCP: recibe un `user_id` y devuelve resultados. `MemoryRepository` usa `SessionProvider.for_user()` en sus diez métodos, así que cada consulta fija `app.current_user_id` y queda sometida a las políticas RLS de `memories`, que además tiene `FORCE ROW LEVEL SECURITY`. `ApiKeyService` opera sobre `SessionProvider.admin()`, donde el bypass de dueño permite gestionar keys.

Esa separación es la que hace viable esta capacidad sin lógica nueva: basta con llamar a los mismos servicios desde una superficie distinta, pasando la identidad que resuelve la sesión web en lugar de la que resuelve la API key.

`MemoryService.update` ya distingue dos operaciones bajo una misma firma. Cambiar importancia, categoría o metadata edita la fila y conserva el identificador. Cambiar contenido retira la memoria original, crea otra con identificador nuevo y embedding nuevo, y las enlaza mediante `superseded_by`. Ámbito y proyecto no son editables por decisión de diseño previa.

`remember` devuelve las memorias similares encontradas. `recall` funde ranking vectorial y textual mediante Reciprocal Rank Fusion y degrada a búsqueda textual cuando Ollama no responde.

## Goals / Non-Goals

**Goals:**

- Dar acceso por navegador a las memorias propias sin duplicar lógica de dominio.
- Hacer visible en la API la diferencia entre corregir y sustituir.
- Exponer la cadena de sustituciones, hoy almacenada pero nunca consultable.
- Permitir a cada usuario gestionar sus propias API keys.
- Ofrecer estadísticas derivadas sin introducir tablas ni contadores.
- Diferenciar indisponibilidad del servicio de embeddings de un fallo genérico.
- Producir un contrato consumible desde otro repositorio.

**Non-Goals:**

- Administrar otros usuarios o sus credenciales.
- Telemetría de uso o estadísticas de actividad de agentes.
- Cambiar la lógica de recuperación, deduplicación o supersesión.
- Permitir mover memorias entre ámbitos o proyectos.
- Exponer embeddings crudos.
- Operaciones por lotes o importación y exportación masiva.

## Decisions

### Corregir y sustituir son dos endpoints, no un `PATCH` polimórfico

La forma obvia es un único `PATCH` que replique la firma de `MemoryService.update`. Se rechaza porque esconde la asimetría más importante del dominio: enviar un campo adicional en el mismo formulario haría que la memoria cambiase de identificador, se retirase la anterior y se recalculara el embedding.

Se separan en dos operaciones: una corrección de atributos que conserva el identificador, y una sustitución explícita que lo crea nuevo. Ambas siguen llamando al mismo método del servicio. La diferencia es que la operación irreversible exige una llamada distinta, de modo que un fallo del cliente no puede jubilar una memoria por accidente.

La respuesta de la sustitución identifica la memoria retirada además de la nueva, porque la interfaz necesita ambas para mostrar lo ocurrido en lugar de un guardado silencioso.

### La cadena de sustituciones se expone como recurso propio

`superseded_by` existe desde la migración `0005` y nunca ha sido consultable. Es el registro de cómo ha cambiado una creencia a lo largo del tiempo, y es lo que distingue a Recallum de un almacén de filas.

Se expone como lectura sobre una memoria concreta, recorriendo el enlace hacia atrás. Al ser una relación entre memorias del mismo usuario, RLS la cubre sin trabajo adicional: un identificador ajeno resulta indistinguible de uno inexistente, igual que ya ocurre en el resto del servicio.

### Emitir una API key exige la contraseña

Es la decisión menos evidente de esta change. Una sesión web dura días y vive en una cookie; una API key no caduca. Si la sesión bastara para emitirla, robar la cookie durante su ventana de validez permitiría acuñar una credencial permanente, y toda la caducidad diseñada en `add-web-session-auth` quedaría anulada por su propia interfaz.

Reintroducir la contraseña en esa operación concreta corta esa escalada. Es fricción deliberada sobre una acción rara: emitir una key ocurre al configurar un cliente nuevo, no a diario.

Revocar no la exige. Revocar reduce el acceso, y ponerle fricción a la operación defensiva es exactamente al revés.

### El secreto se muestra una vez y no se persiste

Se conserva el comportamiento del CLI. La API devuelve el texto de la key sólo en la respuesta de creación y no ofrece forma de recuperarlo, porque sólo se almacena su hash. La interfaz debe advertirlo antes de crearla, no después.

### Las estadísticas se derivan por consulta, sin contadores

Todo lo pedido sale de las memorias del propio usuario: conteos por categoría, ámbito y proyecto; distribución de importancia; series por fecha de creación; volumen a partir de la longitud del contenido más el tamaño fijo de cada vector; y la proporción entre memorias sustituidas y simplemente retiradas, distinguibles porque la sustitución deja `superseded_by`.

Se descartan tablas de agregados o contadores mantenidos por trigger. Con un usuario y un volumen pequeño no compran nada y sí introducen deriva entre el contador y la realidad. Cuando el coste se note, la agregación materializada es una optimización posterior que no cambia el contrato.

Estas consultas van por `for_user()` como el resto: las estadísticas del usuario son suyas y RLS también las cubre.

### La indisponibilidad de embeddings es un estado, no un error genérico

Crear una memoria y sustituir su contenido requieren Ollama; corregir atributos, enumerar, leer y retirar no. La búsqueda funciona degradada a sólo texto.

La API distingue estos tres casos en lugar de devolver un fallo indiferenciado, porque la interfaz que queremos no muestra un cartel de "servicio caído" sino que deshabilita las acciones concretas que no pueden completarse y etiqueta los resultados de búsqueda cuando provienen únicamente del ranking textual. Esa información ya existe dentro del servicio; lo único que falta es no perderla al cruzar la frontera HTTP.

### El contrato se exporta como artefacto versionado

Los repositorios están separados a propósito, así que el sitio web no puede importar tipos del backend. El esquema de la API se exporta a un fichero versionado en este repositorio y se copia al del sitio, que genera desde él su cliente tipado.

Se versiona en ambos lados para que la construcción del sitio no dependa de tener el backend levantado. Una comprobación que regenere y compare detecta cualquier ruptura en el cambio que la introduce, en lugar de en el despliegue del sitio.

### Los límites de paginación son los del dominio

`MemoryLimits` ya acota límites y desplazamientos, y `MemoryService` los aplica. La capa HTTP no define límites propios ni los amplía: recorta a lo que el dominio ya considera aceptable y comunica el valor efectivo cuando difiere del pedido.

## Risks / Trade-offs

- **Separar corrección y sustitución obliga a la interfaz a decidir cuál invoca.** Es intencionado: la alternativa es que decida el servidor a partir de qué campos llegaron, que es precisamente el comportamiento implícito que se quiere evitar.
- **Pedir la contraseña para emitir keys añade fricción y otra verificación con Argon2id.** Se acepta por ser una operación poco frecuente.
- **Las estadísticas por consulta crecerán en coste con el volumen.** Aceptable con un usuario; la ruta de salida existe y no altera el contrato.
- **Las personas pasan a depender de Ollama para escribir.** Antes sólo lo notaban los agentes. Se mitiga exponiendo el estado con precisión, no ocultándolo.
- **El contrato duplicado puede quedar obsoleto** si nadie regenera. Se mitiga con una comprobación automatizada que falle ante divergencias.

## Open Questions

- Si conviene exponer la papelera: `forget` es un borrado lógico y hoy nada permite ver ni restaurar lo retirado.
- Si la vista previa del contexto de sesión, que ya calcula `MemoryService.context`, aporta algo en la interfaz o sólo tiene sentido para agentes.
- Si la búsqueda debe permitir incluir memorias retiradas, útil para auditar pero contrario al filtro de actividad que aplica todo el servicio.
- Qué granularidad temporal usan las series de crecimiento y si la elige el cliente.
