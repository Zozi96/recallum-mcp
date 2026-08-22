## Purpose

Definir un informe administrativo de solo lectura que detecte, para un usuario, memorias activas casi duplicadas agrupables en candidatos de fusión y pares con indicios de contradicción, cerrando el vacío que dejan las advertencias `similar` en tiempo de escritura cuando un agente las ignora.

## Requirements

### Requirement: Informe de higiene del corpus
El sistema MUST ofrecer un comando administrativo de solo lectura (`recallum-admin hygiene --email`) que analice las memorias activas de un usuario y produzca un informe en texto plano con dos secciones: agrupaciones de candidatos de fusión y pares candidatos a contradicción. El comando MUST NOT mutar, fusionar ni olvidar ninguna memoria bajo ninguna circunstancia. El análisis MUST acotar el número de memorias procesadas a un límite configurable (por defecto de orden 500) y el informe MUST declarar explícitamente cuando ese límite recorta el corpus, en vez de truncar en silencio.

#### Scenario: Agrupación de candidatos de fusión por bucket
- **WHEN** existen tres o más memorias activas del mismo ámbito y proyecto cuya similitud semántica por pares supera el umbral configurado
- **THEN** el informe las agrupa en un único clúster de "candidatos de fusión" e incluye, por cada miembro, su identificador abreviado, categoría, importancia y un extracto del contenido, junto con el rango de similitud del clúster

#### Scenario: Los clústeres no cruzan ámbito ni proyecto
- **WHEN** dos memorias con similitud suficiente pertenecen a ámbitos o proyectos distintos
- **THEN** el informe no las incluye en el mismo clúster de candidatos de fusión, porque una fusión solo es válida dentro de un mismo bucket de ámbito y proyecto

#### Scenario: Detección heurística de contradicción
- **WHEN** un par de memorias activas del mismo bucket supera el umbral de similitud y el contenido de una de ellas contiene una expresión de negación o reversión (en inglés o español) que la otra no contiene
- **THEN** el informe lista el par en una sección separada de "candidatos a contradicción", junto con la expresión detectada, etiquetada explícitamente como una heurística para revisión humana o de un agente, nunca como un veredicto automático
