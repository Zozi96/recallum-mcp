## Why

`add-web-session-auth` da identidad de navegador pero ningún dato al que acceder. Sin esta capacidad, el sitio de administración sólo puede iniciar y cerrar sesión.

Las operaciones de memoria existen hoy únicamente como herramientas MCP, pensadas para que las invoque un agente. Persona y agente necesitan cosas distintas del mismo servicio: el agente recupera y guarda durante una sesión de trabajo; la persona necesita revisar qué se ha acumulado, corregirlo, retirar lo que sobra y entender cómo está creciendo. Eso último no lo cubre ninguna herramienta actual y el CLI no lo intenta.

Hay además un momento del producto que hoy se desperdicia. `remember` ya devuelve las memorias similares a lo que se está guardando, precisamente para que las contradicciones afloren donde se crean. Un agente se come esa información en un JSON; una pantalla puede convertirla en una decisión consciente entre sustituir y duplicar.

## What Changes

- Exponer bajo la sesión web las memorias propias: enumeración con filtros y paginación, consulta individual y búsqueda híbrida.
- Permitir crear memorias desde la web devolviendo las memorias similares detectadas, para decidir entre crear una nueva y sustituir una existente.
- Separar en dos operaciones distintas la corrección de atributos, que conserva la identidad de la memoria, y la sustitución de contenido, que retira la memoria anterior y crea otra enlazada a ella.
- Exponer la cadena de sustituciones de una memoria, hoy registrada pero nunca visible.
- Permitir retirar memorias propias.
- Permitir a cada usuario enumerar, emitir y revocar sus propias API keys, mostrando el secreto una única vez.
- Exigir la contraseña para emitir una API key, de modo que una sesión robada no pueda convertirse en una credencial de vida indefinida.
- Ofrecer estadísticas de las memorias propias: distribución por categoría, ámbito, proyecto e importancia, crecimiento en el tiempo, volumen almacenado y proporción de memorias sustituidas frente a retiradas.
- Señalar de forma explícita cuándo una operación no está disponible o está degradada por falta del servicio de embeddings, para que el cliente pueda degradarse por partes en lugar de bloquearse entero.
- Publicar el contrato de la API como artefacto versionado, consumible desde el repositorio del sitio web.

## Capabilities

### New Capabilities

- `web-self-service-api`: Acceso autenticado por sesión web a las memorias, credenciales y estadísticas del propio usuario, con la sustitución de memorias como operación explícita.

### Modified Capabilities

Ninguna. Las herramientas MCP y la lógica de memoria se reutilizan sin cambios de comportamiento.

## Impact

- Reutiliza `MemoryService` y `ApiKeyService` tal cual; no añade lógica de memoria ni toca el repositorio.
- Toda lectura y escritura de memorias sigue pasando por sesiones de base de datos con contexto de usuario, de modo que Row-Level Security continúa siendo la barrera final.
- Añade agregaciones estadísticas sobre las memorias del propio usuario, sin tablas nuevas.
- Introduce dependencia del servicio de embeddings en operaciones iniciadas por una persona, no sólo por agentes, lo que hace visible su indisponibilidad en la interfaz.
- Genera el contrato que consume `recallum-ui`; romperlo se detecta en el repositorio que lo causa.
- No incluye administración de otros usuarios ni telemetría de uso: son changes posteriores.
