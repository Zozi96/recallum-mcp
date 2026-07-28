## 1. Base de la API web

- [x] 1.1 Crear el módulo de rutas de autoservicio bajo `/api/v1/me`, montado en el router `/api/v1` existente.
- [x] 1.2 Implementar la dependencia que resuelve la identidad desde la sesión web y la entrega a los endpoints, sin aceptar ningún identificador de usuario del cliente.
- [x] 1.3 Definir los modelos de entrada y salida con Pydantic, sin exponer embeddings ni hashes.
- [x] 1.4 Definir el mapeo de errores de dominio a respuestas HTTP, diferenciando validación, recurso inexistente, conflicto e indisponibilidad de embeddings.
- [x] 1.5 Añadir pruebas que confirmen que un identificador de usuario enviado por el cliente se ignora.

## 2. Lectura de memorias

- [x] 2.1 Implementar la enumeración con filtros de ámbito, proyecto y categoría, delegando en `MemoryService.list_memories`.
- [x] 2.2 Devolver total, tamaño de página y desplazamiento efectivos, recortados a los límites del dominio.
- [x] 2.3 Implementar la consulta individual, con respuesta indistinguible entre identificador ajeno e inexistente.
- [x] 2.4 Implementar la búsqueda delegando en `MemoryService.recall`.
- [x] 2.5 Propagar el indicador de búsqueda degradada cuando el ranking provenga sólo del texto.
- [x] 2.6 Añadir pruebas de filtros, recorte de paginación y degradación.

## 3. Escritura de memorias

- [x] 3.1 Implementar la creación delegando en `MemoryService.remember`, incluyendo las memorias similares en la respuesta.
- [x] 3.2 Implementar la corrección de atributos limitada a importancia, categoría y metadata, conservando el identificador.
- [x] 3.3 Rechazar de forma explícita cualquier intento de modificar ámbito o proyecto.
- [x] 3.4 Implementar la sustitución de contenido como endpoint separado, devolviendo el identificador retirado y el nuevo.
- [x] 3.5 Implementar la retirada de memorias propias.
- [x] 3.6 Añadir pruebas que confirmen que la corrección de atributos nunca sustituye y que la sustitución siempre crea un identificador nuevo.
- [x] 3.7 Añadir pruebas de duplicado exacto en creación y de colisión de contenido en sustitución.

## 4. Cadena de sustituciones

- [x] 4.1 Añadir al repositorio la consulta que recorre `superseded_by` hacia atrás desde una memoria.
- [x] 4.2 Exponer la cadena como lectura sobre una memoria concreta, en orden temporal.
- [x] 4.3 Añadir prueba de integración que construya una cadena de al menos tres sustituciones y la recupere completa.
- [x] 4.4 Añadir prueba de que la cadena de una memoria ajena responde como inexistente.

## 5. API keys propias

- [x] 5.1 Implementar la enumeración de las keys del usuario de la sesión, sin secretos.
- [x] 5.2 Implementar la emisión con verificación previa de la contraseña, devolviendo el secreto una única vez.
- [x] 5.3 Implementar la revocación limitada a las keys propias, sin exigir contraseña.
- [x] 5.4 Añadir pruebas de que una sesión sin contraseña correcta no puede emitir keys y de que no se puede operar sobre keys ajenas.

## 6. Estadísticas

- [x] 6.1 Añadir al repositorio las agregaciones por categoría, ámbito, proyecto e importancia sobre las memorias del usuario.
- [x] 6.2 Añadir la serie temporal de creación y el cálculo de volumen a partir de la longitud del contenido y el tamaño fijo de cada vector.
- [x] 6.3 Añadir el recuento separado de memorias sustituidas y memorias retiradas.
- [x] 6.4 Exponer el endpoint de estadísticas propias.
- [x] 6.5 Añadir prueba de integración que verifique que las estadísticas no incluyen memorias de otro usuario, con dos usuarios reales de PostgreSQL.
- [x] 6.6 Añadir prueba del caso sin memorias.

## 7. Contrato para el sitio web

- [x] 7.1 Añadir un script que exporte la descripción de la API web a un fichero versionado en el repositorio.
- [x] 7.2 Excluir del artefacto exportado las rutas operativas y el mount de MCP.
- [x] 7.3 Añadir una comprobación que regenere el artefacto y falle si difiere del versionado.
- [x] 7.4 Documentar cómo consume `recallum-ui` este artefacto.

## 8. Verificación transversal

- [x] 8.1 Añadir prueba de integración de aislamiento entre dos usuarios sobre enumeración, búsqueda, lectura individual y estadísticas.
- [x] 8.2 Añadir prueba con el servicio de embeddings caído que confirme qué operaciones siguen disponibles y cuáles fallan de forma distinguible.
- [x] 8.3 Confirmar que ninguna respuesta incluye embeddings, hashes de contenido ni hashes de credenciales.
- [x] 8.4 Confirmar que las herramientas MCP mantienen su comportamiento sin cambios.
