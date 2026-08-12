## ADDED Requirements

### Requirement: Reconfirmación explícita por identificador
El sistema MUST permitir estampar la fecha de reconfirmación de una memoria activa propia a partir de su identificador, sin reescribir el contenido. Identificadores desconocidos, ajenos o retirados MUST reportarse como no reconfirmados, de forma indistinguible.

#### Scenario: Reconfirmar una memoria propia
- **WHEN** el propietario reconfirma una memoria activa por identificador
- **THEN** la memoria conserva el mismo identificador y contenido, y las lecturas posteriores incluyen la nueva fecha de reconfirmación

#### Scenario: Reconfirmar un identificador inexistente o ajeno
- **WHEN** un usuario reconfirma un identificador que no corresponde a una memoria activa propia
- **THEN** el sistema responde como no reconfirmado sin revelar si pertenece a otro usuario
