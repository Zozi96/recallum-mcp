## Why

Recallum permite consultar memorias como registros y agregados, pero no muestra cómo se relacionan temáticamente ni cómo una memoria nueva puede conectar áreas antes aisladas. Una vista de grafo permitirá explorar la memoria personal como un sistema vivo, transversal a categorías y proyectos, sin inventar relaciones que los datos no sostienen.

## What Changes

- Añadir una lectura autenticada del grafo de memorias activas del usuario, con nodos derivados de las memorias y aristas derivadas de su similitud semántica.
- Calcular relaciones temáticas entre proyectos y categorías distintos; permitir componentes aislados cuando no exista evidencia suficiente y puentes cuando una memoria nueva se relacione con varios componentes.
- Mantener acotados los nodos y vecinos devueltos, no exponer embeddings y conservar el aislamiento por usuario en la base de datos.
- Publicar el nuevo contrato en el OpenAPI web versionado para que `recallum-ui` consuma tipos generados.
- Añadir a `recallum-ui` una ruta autenticada de mapa de memoria con navegación, búsqueda, filtros, zoom, paneo, selección y acceso al detalle existente.
- Adaptar una visualización de red densa al lenguaje “Papel Cálido”: formas de categoría ya existentes, tamaño por importancia, proyecto como contexto visual y tierra quemada como único acento.
- Mantener una alternativa navegable para teclado y tecnologías de asistencia, y respetar `prefers-reduced-motion`.
- No persistir transcripts, posiciones visuales ni relaciones arbitrarias; el grafo será una proyección de las memorias y embeddings existentes.

## Capabilities

### New Capabilities

- `memory-graph`: Lectura privada y visualización interactiva del grafo temático de memorias activas del usuario.

### Modified Capabilities

Ninguna.

## Impact

- Backend: modelos de respuesta, servicio/repositorio de memorias, rutas de autoservicio y pruebas de aislamiento y contrato.
- Contrato: `openapi/web-v1.json` y tipos generados usados por la UI.
- Frontend: repositorio hermano `recallum-ui`, incluyendo router, navegación, cliente API, nueva vista del grafo, estilos y pruebas de interacción y accesibilidad.
- Rendimiento: cálculo acotado de similitudes entre memorias activas; no se añade una tabla de aristas.
- Dependencias: puede requerirse una dependencia enfocada únicamente en el layout del grafo si el layout nativo mínimo no ofrece estabilidad e interacción suficientes.
