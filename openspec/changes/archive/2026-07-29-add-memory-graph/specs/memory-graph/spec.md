## Purpose

Definir una lectura privada y una representación interactiva del grafo temático formado por las memorias activas de un usuario, mostrando tanto componentes aislados como puentes descubiertos con el crecimiento de su memoria.

## ADDED Requirements

### Requirement: Lectura privada del grafo
El sistema MUST exigir una sesión web válida para consultar el grafo, MUST derivar el propietario exclusivamente de esa sesión y MUST ejecutar la lectura con el aislamiento por usuario de la base de datos. El contrato MUST NOT aceptar un identificador de usuario ni exponer los embeddings almacenados.

#### Scenario: Consulta autenticada
- **WHEN** un usuario con una sesión válida solicita su grafo
- **THEN** el sistema devuelve únicamente nodos y relaciones derivados de sus propias memorias

#### Scenario: Sesión ausente o inválida
- **WHEN** una petición del grafo llega sin una sesión válida
- **THEN** el sistema la rechaza antes de consultar las memorias

#### Scenario: Memorias de otro usuario
- **WHEN** existen memorias temáticamente similares pertenecientes a otro usuario
- **THEN** no aparecen como nodos ni participan en ninguna relación del grafo

#### Scenario: Datos vectoriales privados
- **WHEN** el sistema devuelve un grafo
- **THEN** la respuesta no contiene embeddings ni otro dato interno necesario sólo para calcular similitud

### Requirement: Nodos de memorias activas
El grafo MUST representar memorias activas globales y de cualquier proyecto como nodos de una única memoria personal. Cada nodo MUST identificar la memoria y proporcionar el contenido, categoría, ámbito, proyecto opcional, importancia y fecha de creación necesarios para presentarla y abrir su detalle.

#### Scenario: Vista general
- **WHEN** se consulta el grafo sin filtros
- **THEN** el conjunto candidato incluye memorias activas globales y de todos los proyectos del usuario

#### Scenario: Memorias retiradas o sustituidas
- **WHEN** existen memorias retiradas o sustituidas
- **THEN** no aparecen como nodos del grafo activo

#### Scenario: Filtro de contexto
- **WHEN** el usuario filtra por ámbito, proyecto o categoría
- **THEN** el sistema devuelve un grafo formado únicamente por las memorias activas que cumplen esos filtros

#### Scenario: Acceso al registro original
- **WHEN** el usuario activa un nodo
- **THEN** puede abrir la ficha existente de la memoria identificada por ese nodo

### Requirement: Relaciones temáticas sin fronteras de proyecto
El sistema MUST crear una relación únicamente cuando dos memorias comparables superen la evidencia mínima de similitud temática. La categoría, el ámbito y el proyecto MUST NOT impedir una relación ni crearla por sí solos. Cada relación MUST identificar sus dos extremos y comunicar su fuerza de similitud.

#### Scenario: Relación entre proyectos
- **WHEN** dos memorias de proyectos distintos tienen suficiente similitud temática
- **THEN** el grafo contiene una relación entre sus nodos

#### Scenario: Relación entre categorías
- **WHEN** una decisión y una restricción tienen suficiente similitud temática
- **THEN** el grafo puede relacionarlas aunque sus categorías sean distintas

#### Scenario: Coincidencia administrativa sin relación temática
- **WHEN** dos memorias comparten proyecto o categoría pero no alcanzan la similitud mínima
- **THEN** el sistema no crea una relación entre ellas

#### Scenario: Embeddings no comparables
- **WHEN** dos memorias fueron vectorizadas con modelos cuya procedencia no permite compararlas con fiabilidad
- **THEN** el sistema no crea una relación entre ellas e indica que el grafo puede ser parcial

### Requirement: Componentes aislados y memorias puente
El grafo MUST admitir nodos y componentes desconectados. Una memoria persistida posteriormente MUST poder unir componentes anteriores cuando sea temáticamente cercana a memorias de más de uno, sin crear una relación directa que no esté respaldada por similitud.

#### Scenario: Proyecto aislado
- **WHEN** las memorias de un proyecto no se relacionan suficientemente con el resto
- **THEN** aparecen como un componente separado o como nodos aislados

#### Scenario: Nueva memoria puente
- **WHEN** una memoria nueva es similar a memorias situadas en dos componentes antes separados
- **THEN** la siguiente lectura del grafo la conecta con ambos componentes

#### Scenario: Relación conversada pero no conservada
- **WHEN** una sesión menciona una relación entre temas pero no persiste ninguna memoria nueva
- **THEN** el grafo no cambia por el contenido transitorio de esa conversación

### Requirement: Grafo acotado y honesto
El sistema MUST limitar el número de nodos y de relaciones para mantener una respuesta y visualización manejables, MUST priorizar las relaciones temáticas más fuertes y MUST indicar el total disponible y si la lectura fue truncada. Los límites MUST NOT provocar conexiones artificiales.

#### Scenario: Memoria dentro del límite
- **WHEN** todas las memorias candidatas caben en el límite efectivo
- **THEN** la respuesta indica que el grafo no fue truncado

#### Scenario: Memoria mayor que el límite
- **WHEN** existen más memorias candidatas que las permitidas
- **THEN** el sistema devuelve un subconjunto determinista, comunica el total y marca la respuesta como truncada

#### Scenario: Componente muy denso
- **WHEN** un nodo supera el máximo de vecinos presentables
- **THEN** el sistema conserva sus relaciones más fuertes dentro del límite

#### Scenario: Nodo sin relación suficiente
- **WHEN** ninguna relación de un nodo supera la evidencia mínima
- **THEN** el nodo permanece visible sin que el sistema le asigne un vecino artificial

### Requirement: Representación coherente con Recallum
La UI MUST ofrecer una ruta autenticada y una entrada de navegación para el mapa de memoria. La vista MUST conservar el lenguaje visual “Papel Cálido” en modos claro y oscuro, MUST representar la categoría mediante las formas geométricas existentes, MUST representar la importancia mediante tamaño y MUST reservar el acento de tierra quemada para estados destacados.

#### Scenario: Codificación de categoría
- **WHEN** aparecen memorias de categorías distintas
- **THEN** sus nodos utilizan las formas de preferencia, decisión, restricción y hecho ya definidas por la interfaz

#### Scenario: Codificación de importancia
- **WHEN** dos nodos tienen distinta importancia
- **THEN** la diferencia se refleja mediante una escala de tamaño acotada sin ocultar el valor textual en el detalle

#### Scenario: Contexto de proyecto
- **WHEN** el usuario inspecciona o selecciona un nodo de proyecto
- **THEN** la UI identifica el proyecto sin tratarlo como evidencia de una relación temática

#### Scenario: Modos de color
- **WHEN** cambia la preferencia de color del sistema
- **THEN** el lienzo, nodos, aristas, controles y estados usan los tokens claro u oscuro existentes

### Requirement: Exploración del grafo
La vista MUST permitir buscar entre los nodos cargados, aplicar filtros de ámbito, proyecto y categoría, desplazar y ampliar el lienzo, recentrar la composición y seleccionar una memoria sin perder el contexto del grafo.

#### Scenario: Seleccionar una memoria
- **WHEN** el usuario selecciona un nodo
- **THEN** la UI destaca ese nodo y sus relaciones y muestra un resumen con acceso a la ficha completa

#### Scenario: Buscar contenido visible
- **WHEN** el usuario busca texto presente en uno o más nodos cargados
- **THEN** la UI destaca los resultados sin afirmar que ha buscado fuera de una respuesta truncada

#### Scenario: Aplicar un filtro
- **WHEN** el usuario cambia un filtro de ámbito, proyecto o categoría
- **THEN** la vista solicita o presenta el subgrafo correspondiente y comunica el número de nodos visibles

#### Scenario: Recuperar la orientación
- **WHEN** el usuario ha desplazado o ampliado el lienzo
- **THEN** puede recentrar el grafo completo mediante un control visible

### Requirement: Crecimiento estable y actualización explícita
La vista MUST tratar el grafo como una instantánea actualizable, MUST incorporar memorias nuevas tras una actualización y MUST conservar en lo posible la posición de los nodos ya visibles durante la misma sesión. La UI MUST NOT presentar la lectura como tiempo real.

#### Scenario: Memoria incorporada por un agente
- **WHEN** se actualiza el grafo después de que un agente haya persistido una memoria
- **THEN** la memoria aparece como nodo y adopta las relaciones temáticas que correspondan

#### Scenario: Actualización con memoria puente
- **WHEN** una memoria nueva conecta componentes existentes
- **THEN** los nodos anteriores conservan una orientación reconocible mientras el nodo nuevo ocupa una posición entre sus vecinos

#### Scenario: Datos sin actualizar
- **WHEN** la vista muestra una instantánea que todavía no se ha refrescado
- **THEN** la UI no afirma que refleja cambios en vivo

### Requirement: Accesibilidad y movimiento
Toda información y acción esencial del grafo MUST estar disponible mediante teclado y tecnologías de asistencia sin depender únicamente de color, posición o gesto de puntero. La vista MUST respetar `prefers-reduced-motion` y MUST ofrecer una forma estructurada de recorrer las memorias visibles.

#### Scenario: Navegación por teclado
- **WHEN** una persona usa únicamente el teclado
- **THEN** puede recorrer o buscar nodos, seleccionar una memoria, abrir su ficha y accionar los controles del lienzo

#### Scenario: Lector de pantalla
- **WHEN** una persona explora la vista con tecnología de asistencia
- **THEN** recibe el contenido, categoría, importancia, proyecto y número de relaciones de cada memoria accesible

#### Scenario: Categoría sin color
- **WHEN** una persona no distingue el color del nodo
- **THEN** puede reconocer su categoría por la forma y por una etiqueta textual

#### Scenario: Movimiento reducido
- **WHEN** el sistema solicita movimiento reducido
- **THEN** el grafo se presenta en una disposición estable sin animación de simulación ni transiciones no esenciales

### Requirement: Estados vacíos, parciales y de error
La UI MUST distinguir entre una memoria vacía, un grafo con nodos sin relaciones, una lectura parcial o truncada y un fallo de carga. Un fallo del grafo MUST NOT impedir navegar al resto de las vistas autenticadas.

#### Scenario: Usuario sin memorias
- **WHEN** el grafo no contiene nodos
- **THEN** la UI muestra un estado vacío con acceso a crear la primera memoria

#### Scenario: Memorias sin relaciones
- **WHEN** existen nodos pero ninguna relación supera el umbral
- **THEN** la UI muestra los nodos aislados y explica que todavía no hay conexiones temáticas

#### Scenario: Grafo parcial o truncado
- **WHEN** la respuesta indica incompatibilidad de embeddings o truncamiento
- **THEN** la UI mantiene la visualización y comunica claramente la limitación

#### Scenario: Fallo de carga
- **WHEN** no se puede recuperar el grafo
- **THEN** la UI muestra un error recuperable y permite reintentar sin abandonar la aplicación
