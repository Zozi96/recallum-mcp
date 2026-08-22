## ADDED Requirements

### Requirement: Cola stale y vecinos en self-service
La API self-service autenticada MUST permitir al propietario listar memorias stale de su cuenta y obtener vecinos temáticos acotados de una memoria activa propia, sin exponer embeddings ni memorias ajenas. Las mutaciones de desenlace (`reconfirm`, corrección, borrado, merge) MUST reutilizar las mismas semánticas de dominio que las herramientas MCP equivalentes cuando estén expuestas por HTTP.

#### Scenario: Listar cola stale
- **WHEN** el propietario autenticado solicita la cola stale
- **THEN** recibe sólo sus memorias activas cuya confirmación supera el umbral de staleness, sin vectores

#### Scenario: Vecinos de una semilla propia
- **WHEN** el propietario solicita vecinos de una memoria activa propia
- **THEN** recibe una lista acotada de vecinos temáticos sin embeddings

#### Scenario: Semilla ajena o retirada
- **WHEN** el propietario solicita vecinos de un id desconocido, ajeno o retirado
- **THEN** la respuesta es vacía o no encontrada de forma que no revele pertenencia cruzada
