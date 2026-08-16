## ADDED Requirements

### Requirement: Detección de desfase docs↔superficie MCP
El gate rápido de entrega MUST comprobar que la documentación pública que enumera herramientas MCP coincide con el conjunto publicado por el servidor (once herramientas con los nombres canónicos). Un desfase MUST fallar el gate indicando el artefacto documental a corregir.

#### Scenario: Docs alineadas
- **WHEN** el README (y guías de superficie incluidas en el check) listan exactamente las once herramientas canónicas
- **THEN** el gate rápido no falla por superficie MCP

#### Scenario: Docs desfasadas
- **WHEN** la documentación pública afirma un conteo distinto u omite una herramienta publicada
- **THEN** CI falla nombrando el documento y el desfase
