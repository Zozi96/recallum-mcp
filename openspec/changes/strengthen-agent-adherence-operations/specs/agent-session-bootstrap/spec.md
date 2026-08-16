## ADDED Requirements

### Requirement: Equivalencia contractual del ciclo con el benchmark
La guía de ciclo de memoria en `SessionStart` MUST permanecer alineada con los nombres de herramienta y el comportamiento fail-open que el benchmark observado asume por cliente, de modo que una mejora del runbook o de la matriz no contradiga el recordatorio inyectado.

#### Scenario: Nombre de herramienta coherente
- **WHEN** el benchmark observa un cliente concreto
- **THEN** la guía de `SessionStart` de ese cliente nombra las mismas herramientas de context/recall/captura que el escenario espera descubrir

#### Scenario: Fail-open intacto
- **WHEN** el servidor de memoria no está disponible al iniciar
- **THEN** la guía de ciclo sigue siendo emitida sin bloquear la sesión, igual que el benchmark trata omisiones sin fabricar éxito
