## ADDED Requirements

### Requirement: Context nunca sirve perfil anterior a la última mutación
Cuando `context` incluye el perfil materializado, la respuesta MUST NOT ser más vieja que la última
mutación confirmada del usuario, aunque la reconstrucción del perfil sea diferida. Si la generación
materializada difiere de la del corpus, la lectura MUST reconstruir el slice static en el momento
antes de responder.

#### Scenario: Context tras mutación pendiente de rebuild
- **WHEN** un usuario guarda o borra una memoria y llama `context` antes de que el trabajador de reconstrucción complete
- **THEN** la respuesta refleja la mutación, sin esperar al trabajador
