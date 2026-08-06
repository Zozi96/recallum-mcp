## ADDED Requirements

### Requirement: Ciclo de memoria visible al iniciar sesión
Cada salida de `SessionStart` MUST exponer al agente un ciclo breve y accionable de tres momentos: usar el contexto inicial o digest disponible, ejecutar un único `recall` enfocado cuando cambie materialmente el subsistema, hipótesis o decisión y la memoria durable pueda afectar la siguiente acción, y capturar al finalizar sólo contexto reutilizable verificado. La guía MUST usar los nombres de herramienta visibles para el cliente activo y MUST conservar las reglas de consulta inglesa del delta, proyecto canónico, `limit=3`, supresión cuando el contexto activo ya sea suficiente y continuidad fail-open.

#### Scenario: Inicio sin digest
- **WHEN** el hook emite la instrucción estándar porque no obtuvo un digest
- **THEN** la salida indica cargar `context` con el proyecto y foco de tarea, describe el checkpoint semántico y conserva la captura final

#### Scenario: Inicio con digest disponible
- **WHEN** el hook inyecta un digest compacto del proyecto
- **THEN** la salida evita pedir otro `context` genérico, pero conserva el checkpoint semántico para un foco nuevo y la captura final

#### Scenario: Proyecto todavía sin memorias
- **WHEN** el servidor confirma que el proyecto no tiene memorias almacenadas al iniciar
- **THEN** la salida omite la carga inicial innecesaria y mantiene la guía para recuperar ante un pivote posterior y capturar hallazgos al terminar

#### Scenario: Contexto activo suficiente
- **WHEN** el contexto inicial o digest ya contiene la memoria necesaria para la decisión siguiente
- **THEN** la guía exige aplicar y verificar ese contexto sin ejecutar un `recall` redundante

#### Scenario: Nombres de herramienta por cliente
- **WHEN** el hook se ejecuta en Codex, Claude Code o Grok Build
- **THEN** el ciclo breve nombra las herramientas según el prefijo y mecanismo de descubrimiento del cliente correspondiente
