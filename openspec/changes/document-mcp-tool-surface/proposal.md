## Why

La superficie MCP real ya publica once herramientas (`related_memories` y `reconfirm` incluidas), pero la documentación de entrada del proyecto todavía describe nueve. Ese desfase hace que operadores y agentes descubran capacidades incompletas y debilita el contrato de entrega.

## What Changes

- Exigir que la documentación pública del repositorio (README y guías de cliente referenciadas) liste exactamente el mismo conjunto de herramientas MCP que el servidor anuncia.
- Añadir verificación contractual ligera para que el desfase docs↔superficie no vuelva a pasar desapercibido en el gate de entrega.
- No cambiar el runtime MCP, esquemas, prompts ni comportamiento de herramientas.

## Capabilities

### New Capabilities

Ninguna.

### Modified Capabilities

- `mcp-agent-integration`: La documentación pública del conjunto de herramientas MUST coincidir con las once herramientas publicadas.
- `delivery-verification`: El gate de entrega MUST detectar desalineación entre docs de superficie MCP y el anuncio del servidor.

## Impact

- Afecta `README.md`, posiblemente `docs/clients.md`, y pruebas o checks de entrega documentales.
- No altera FastMCP, autenticación, persistencia ni ranking.
